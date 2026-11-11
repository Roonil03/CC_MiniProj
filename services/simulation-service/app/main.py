"""Simulation-service HTTP surface (Member-4).

Thin FastAPI wrapper over the counterfactual simulator: evaluates candidate
actions against twin state supplied in the request. Propose-only.
"""

from __future__ import annotations

import os
import math
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field, field_validator

from .simulator import evaluate_candidates
from .twin import TwinState

app = FastAPI(title="dt-ram simulation-service")


@app.middleware("http")
async def service_auth(request: Request, call_next):
    token = os.getenv("DT_RAM_SERVICE_TOKEN")
    if token and request.url.path not in {"/healthz", "/readyz"}:
        if request.headers.get("x-service-token") != token:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


class SimulateRequest(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    service_cpu: float = Field(default=0.5, ge=0)
    service_mem_mb: float = Field(default=512.0, ge=0)
    predicted: dict[str, Any] = Field(default_factory=dict)
    dt_fidelity: float = Field(default=0.0, ge=0, le=1)
    forecast_horizon_seconds: int = Field(default=5, ge=1, le=3600)

    @field_validator("nodes")
    @classmethod
    def validate_nodes(cls, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for node in nodes:
            if not isinstance(node.get("node_id"), str) or not node["node_id"].strip():
                raise ValueError("each node requires a non-empty node_id")
            if "cpu" not in node and not {"cpu_used", "cpu_total"}.issubset(node):
                raise ValueError("cpu or cpu_used with cpu_total is required")
            if "memory" not in node and not {"memory_used_mb", "memory_total_mb"}.issubset(node):
                raise ValueError("memory or memory_used_mb with memory_total_mb is required")
            if "network_in" not in node and "network_in_mbps" not in node:
                raise ValueError("network_in measurement is required")
            if "network_out" not in node and "network_out_mbps" not in node:
                raise ValueError("network_out measurement is required")
            for key in ("cpu", "memory"):
                if key in node and not 0 <= _finite_number(node[key], key) <= 1:
                    raise ValueError(f"{key} utilization must be in [0,1]")
            for key in ("cpu_total", "memory_total_mb"):
                if key in node and _finite_number(node[key], key) <= 0:
                    raise ValueError(f"{key} must be positive")
            for key in ("cpu_used", "memory_used_mb", "network_in", "network_out",
                        "network_in_mbps", "network_out_mbps"):
                if key in node and _finite_number(node[key], key) < 0:
                    raise ValueError(f"{key} must be non-negative")
            for used_key, total_key, utilization_key in (
                ("cpu_used", "cpu_total", "cpu"),
                ("memory_used_mb", "memory_total_mb", "memory"),
            ):
                if used_key in node and utilization_key not in node:
                    total = _finite_number(node.get(total_key, 8.0 if used_key == "cpu_used" else 16384.0), total_key)
                    if _finite_number(node[used_key], used_key) / total > 1:
                        raise ValueError(f"{used_key} cannot exceed {total_key}")
            if "stale" in node and not isinstance(node["stale"], bool):
                raise ValueError("stale must be a boolean")
            if "health" in node and not isinstance(node["health"], str):
                raise ValueError("health must be a string")
            if node.get("timestamp") is not None:
                _parse_timestamp(node["timestamp"])
        return nodes

    @field_validator("candidates")
    @classmethod
    def validate_candidates(cls, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        supported = {"NOOP", "MIGRATE", "PLACE", "SCALE", "RESOURCE_ADJUST"}
        for candidate in candidates:
            action_type = candidate.get("type", "NOOP")
            if not isinstance(action_type, str) or action_type.upper() not in supported:
                raise ValueError(f"unsupported candidate action type: {action_type}")
            for key in ("source", "destination", "service", "serviceId"):
                if key in candidate and not isinstance(candidate[key], str):
                    raise ValueError(f"{key} must be a string")
            if "replicas" in candidate:
                replicas = candidate["replicas"]
                if isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 1:
                    raise ValueError("replicas must be a positive integer")
            if action_type.upper() in {"NOOP", "MIGRATE", "SCALE", "RESOURCE_ADJUST"} and not candidate.get("source"):
                raise ValueError(f"{action_type} requires source")
            if action_type.upper() in {"MIGRATE", "PLACE"} and not candidate.get("destination"):
                raise ValueError(f"{action_type} requires destination")
            if action_type.upper() == "SCALE" and "replicas" not in candidate:
                raise ValueError("SCALE requires replicas")
            if "bandwidth_mbps" in candidate and _finite_number(candidate["bandwidth_mbps"], "bandwidth_mbps") <= 0:
                raise ValueError("bandwidth_mbps must be positive")
            if "state_mb" in candidate and _finite_number(candidate["state_mb"], "state_mb") < 0:
                raise ValueError("state_mb must be nonnegative")
            for key in ("cpu_delta", "cpuDelta", "memory_delta_mb", "memoryDelta"):
                if key in candidate:
                    _finite_number(candidate[key], key)
        return candidates

    @field_validator("predicted")
    @classmethod
    def validate_prediction(cls, predicted: dict[str, Any]) -> dict[str, Any]:
        if "prediction_confidence" in predicted:
            confidence = _finite_number(predicted["prediction_confidence"], "prediction_confidence")
            if not 0 <= confidence <= 1:
                raise ValueError("prediction_confidence must be in [0,1]")
        seen = set()
        for forecast in predicted.get("forecasts", []):
            if not isinstance(forecast, dict) or not all(forecast.get(key) for key in ("node_id", "metric", "timestamp", "source")):
                raise ValueError("forecast requires node_id, metric, timestamp and source")
            if forecast["metric"] not in {"cpu", "memory"}:
                raise ValueError("forecast metric must be cpu or memory")
            if not isinstance(forecast.get("horizon_seconds"), int) or forecast["horizon_seconds"] <= 0:
                raise ValueError("forecast horizon_seconds must be positive")
            if not 0 <= _finite_number(forecast.get("value"), "forecast value") <= 1:
                raise ValueError("forecast value must be a utilization fraction")
            key = (forecast["node_id"], forecast["metric"], forecast["horizon_seconds"])
            if key in seen:
                raise ValueError("duplicate forecast for node, metric and horizon")
            seen.add(key)
            _parse_timestamp(forecast["timestamp"])
        return predicted


def _finite_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be an ISO-8601 datetime") from exc
    else:
        raise ValueError("timestamp must be an ISO-8601 datetime")
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "simulation-service"}


@app.get("/readyz")
def readyz() -> dict:
    return {"status": "ok", "service": "simulation-service"}


@app.post("/simulate")
def simulate(req: SimulateRequest) -> dict:
    twin = TwinState()
    for n in req.nodes:
        cpu_total = float(n.get("cpu_total", 8.0))
        memory_total_mb = float(n.get("memory_total_mb", 16384.0))
        timestamp = _parse_timestamp(n["timestamp"]) if n.get("timestamp") is not None else None
        twin.apply_telemetry(
            node_id=n.get("node_id", ""),
            cpu_util=float(n["cpu"]) if "cpu" in n else float(n.get("cpu_used", 0.0)) / cpu_total,
            mem_util=float(n["memory"]) if "memory" in n else float(n.get("memory_used_mb", 0.0)) / memory_total_mb,
            network_in_mbps=float(n.get("network_in", n.get("network_in_mbps"))),
            network_out_mbps=float(n.get("network_out", n.get("network_out_mbps"))),
            cpu_total=cpu_total,
            memory_total_mb=memory_total_mb,
            health=str(n.get("health", "healthy")),
            timestamp=timestamp,
            stale=bool(n.get("stale", False)) or timestamp is None,
        )
    forecast_overrides = {}
    applied_forecasts = []
    now = datetime.now(timezone.utc)
    for forecast in req.predicted.get("forecasts", []):
        timestamp = _parse_timestamp(forecast["timestamp"]).astimezone(timezone.utc)
        if (forecast["horizon_seconds"] == req.forecast_horizon_seconds
                and 0 <= (now - timestamp).total_seconds() <= 5
                and twin.get_node(forecast["node_id"]) is not None):
            forecast_overrides[(forecast["node_id"], forecast["metric"])] = float(forecast["value"])
            applied_forecasts.append(forecast)
    results = evaluate_candidates(
        twin,
        req.candidates,
        service_cpu=req.service_cpu,
        service_mem_mb=req.service_mem_mb,
        forecast_overrides=forecast_overrides,
    )
    return {
        "applied_forecasts": applied_forecasts,
        "results": [
            {
                "action_type": r.action_type,
                "predicted_cpu": r.predicted_cpu,
                "predicted_mem": r.predicted_mem,
                "predicted_latency_ms": r.predicted_latency_ms,
                "slo_violation_prob": r.slo_violation_prob,
                "migration_cost": r.migration_cost,
                "migration_duration_s": r.migration_duration_s,
                "feasible": r.feasible,
                "notes": r.notes,
                "prediction_confidence": req.predicted.get("prediction_confidence", 0.0),
                "dt_fidelity": req.dt_fidelity,
            }
            for r in results
        ]
    }
