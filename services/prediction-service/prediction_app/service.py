"""Read-only prediction API for the existing gateway routes."""

from __future__ import annotations

import os
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Query, Request

from .data import METRICS, SampleStore, format_time
from .features import bucketed
from .models import persistence, predict_neural
from .registry import Registry

UNITS = {"cpu": "fraction", "memory": "fraction",
         "network_in": "Mbps", "network_out": "Mbps"}


def create_app(*, db_path: str | Path | None = None,
               registry_path: str | Path | None = None,
               now: Callable[[], datetime] | None = None) -> FastAPI:
    db_path = db_path or os.getenv("PREDICTION_DATA_PATH", "data/node_samples.sqlite")
    registry_path = registry_path or os.getenv("PREDICTION_REGISTRY_PATH", "models_saved/registry.json")
    max_age = float(os.getenv("PREDICTION_MAX_AGE_SECONDS", "5"))
    if not math.isfinite(max_age) or max_age <= 0:
        raise ValueError("PREDICTION_MAX_AGE_SECONDS must be finite and positive")
    clock = now or (lambda: datetime.now(timezone.utc))
    registry = Registry(registry_path)
    loaded_models: dict[tuple[str, str], tuple] = {}
    api = FastAPI(title="DT-RAM prediction service")

    @api.middleware("http")
    async def service_auth(request: Request, call_next):
        token = os.getenv("DT_RAM_SERVICE_TOKEN")
        if token and request.url.path not in ("/healthz", "/readyz"):
            if request.headers.get("x-service-token") != token:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    @api.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "prediction-service"}

    @api.get("/readyz")
    def readyz():
        store = SampleStore(db_path)
        try:
            ready = any(
                bool(samples := store.recent(node, 1))
                and -max_age <= (clock() - samples[-1].timestamp).total_seconds() <= max_age
                for node in store.nodes())
        finally:
            store.close()
        if not ready:
            raise HTTPException(503, "no fresh telemetry recorded")
        return {"status": "ok"}

    @api.get("/models")
    def models():
        active = registry.active()
        return {"models": [{**record, "active": active.get(record["metric"]) == record["model_id"]}
                           for record in registry.records()]}

    @api.get("/predictions")
    def predictions(node_id: str | None = None,
                    metric: str | None = Query(default=None)):
        if metric is not None and metric not in METRICS:
            raise HTTPException(422, "unsupported metric")
        store = SampleStore(db_path)
        try:
            nodes = [node_id] if node_id else store.nodes()
            recent = {node: store.recent(node, 180) for node in nodes}
        finally:
            store.close()
        output, errors = [], []
        for node, samples in recent.items():
            if not samples:
                errors.append({"node_id": node, "reason": "unknown node or no history"})
                continue
            origin = samples[-1].timestamp
            age = (clock() - origin).total_seconds()
            if age < -max_age or age > max_age:
                errors.append({"node_id": node, "reason": "stale or future telemetry"})
                continue
            for target in ((metric,) if metric else METRICS):
                try:
                    record = registry.selected(target)
                    if record is None:
                        horizons, period, required = (5, 10, 30, 60), 1, 1
                        model_id = "persistence-unregistered"
                        confidence, calibration = {}, {}
                    else:
                        config = record["hyperparameters"]
                        horizons = tuple(config["horizons_seconds"])
                        period = config["period_seconds"]
                        required = config["history_steps"]
                        model_id = record["model_id"]
                        confidence = record["confidence"]
                        calibration = record["calibration"]
                    buckets = bucketed(samples, period)[node]
                    origin_bucket = max(buckets)
                    forecast_origin = datetime.fromtimestamp(origin_bucket * period, timezone.utc)
                    keys = range(origin_bucket - required + 1, origin_bucket + 1)
                    if not all(key in buckets for key in keys):
                        raise ValueError("insufficient contiguous history")
                    history = tuple(getattr(buckets[key], target) for key in keys)
                    if record is None or record["kind"] == "persistence":
                        values = persistence(history, horizons)
                    else:
                        key = (record["model_id"], record["artifact_hash"])
                        if key not in loaded_models:
                            loaded_models[key] = registry.load_network(record)
                        network, scale = loaded_models[key]
                        values = predict_neural(network, scale, history)
                    for horizon, value in zip(horizons, values):
                        if target in ("cpu", "memory"):
                            value = max(0.0, min(1.0, value))
                        else:
                            value = max(0.0, value)
                        radius = calibration.get(str(horizon), {}).get("radius")
                        quality = confidence.get(str(horizon), {}).get("coverage_lower_bound")
                        lower = max(0.0, value - radius) if radius is not None else None
                        upper = value + radius if radius is not None else None
                        if target in ("cpu", "memory") and upper is not None:
                            upper = min(1.0, upper)
                        output.append({"node_id": node, "metric": target, "unit": UNITS[target],
                                       "origin_timestamp": format_time(forecast_origin),
                                       "latest_observation_timestamp": format_time(origin),
                                       "target_timestamp": format_time(forecast_origin + timedelta(seconds=horizon)),
                                       "horizon_seconds": horizon, "value": value,
                                       "lower_bound": lower, "upper_bound": upper,
                                       "confidence": quality,
                                       "confidence_basis": "validation_interval_coverage_lower_bound"
                                       if quality is not None else None,
                                       "model_id": model_id,
                                       "status": "calibrated" if quality is not None else "uncalibrated"})
                except (ValueError, OSError, KeyError, ImportError) as exc:
                    errors.append({"node_id": node, "metric": target, "reason": str(exc)})
        if not output:
            raise HTTPException(503, {"status": "unavailable", "errors": errors})
        status = "degraded" if errors or any(p["status"] != "calibrated" for p in output) else "ok"
        return {"status": status, "predictions": output, "errors": errors}

    return api


app = create_app()
