"""Simulation-service HTTP surface (Member-4).

Thin FastAPI wrapper over the counterfactual simulator: evaluates candidate
actions against twin state supplied in the request. Propose-only.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

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
    nodes: list[dict] = Field(default_factory=list)
    candidates: list[dict] = Field(default_factory=list)
    service_cpu: float = 0.5
    service_mem_mb: float = 512.0
    predicted: dict = Field(default_factory=dict)
    dt_fidelity: float = 0.0


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
        twin.apply_telemetry(
            node_id=n.get("node_id", ""),
            cpu_util=float(n.get("cpu", 0.0)),
            mem_util=float(n.get("memory", 0.0)),
            network_in_mbps=float(n.get("network_in", 0.0)),
            network_out_mbps=float(n.get("network_out", 0.0)),
            cpu_total=float(n.get("cpu_total", 8.0)),
            memory_total_mb=float(n.get("memory_total_mb", 16384.0)),
            health=str(n.get("health", "healthy")),
        )
    results = evaluate_candidates(
        twin,
        req.candidates,
        service_cpu=req.service_cpu,
        service_mem_mb=req.service_mem_mb,
    )
    return {
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
