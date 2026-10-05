"""Simulation-service HTTP surface (Member-4).

Thin FastAPI wrapper over the counterfactual simulator: evaluates candidate
actions against twin state supplied in the request. Propose-only.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .simulator import evaluate_candidates
from .twin import TwinState

app = FastAPI(title="dt-ram simulation-service")


class SimulateRequest(BaseModel):
    nodes: list[dict] = Field(default_factory=list)
    candidates: list[dict] = Field(default_factory=list)
    service_cpu: float = 0.5
    service_mem_mb: float = 512.0


@app.get("/healthz")
def healthz() -> dict:
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
                "predicted_latency_ms": r.predicted_latency_ms,
                "slo_violation_prob": r.slo_violation_prob,
                "migration_cost": r.migration_cost,
                "feasible": r.feasible,
                "notes": r.notes,
            }
            for r in results
        ]
    }
