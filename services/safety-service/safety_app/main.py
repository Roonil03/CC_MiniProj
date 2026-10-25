"""Safety-service HTTP stub (Member-2 + Member-4 shared).

Thin FastAPI gate on SAFETY_SERVICE_PORT=5003. Reuses the canonical gate
logic owned by simulation-service; thresholds stay in one place.
"""

from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "simulation-service"))

from app.safety import GateConfig, SafetyGate  # noqa: E402

app = FastAPI(title="dt-ram safety-service")


class ValidateRequest(BaseModel):
    action: dict = Field(default_factory=dict)
    predicted: dict = Field(default_factory=dict)
    dt_fidelity: float = 0.0
    destination_free_cpu: float = 0.0
    destination_healthy: bool = False
    source_healthy: bool = False


class ApproveRequest(ValidateRequest):
    decision_id: str
    policy_version: str
    execution_mode: str = "shadow"


gate = SafetyGate(GateConfig())


@app.middleware("http")
async def service_auth(request: Request, call_next):
    token = os.getenv("DT_RAM_SERVICE_TOKEN")
    if token and request.url.path not in {"/healthz", "/readyz"}:
        if request.headers.get("x-service-token") != token:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "safety-service"}


@app.get("/readyz")
def readyz() -> dict:
    return {"status": "ok", "service": "safety-service"}


@app.get("/policies")
def policies() -> dict:
    config = gate.config
    return {
        "min_fidelity": config.min_fidelity,
        "min_prediction_confidence": config.min_confidence,
        "max_slo_probability": config.max_slo_prob,
        "max_migrations_per_minute": config.max_migrations_per_minute,
        "node_cooldown_seconds": config.node_cooldown_seconds,
        "execution_modes": ["shadow"],
        "supported_actions": ["NOOP", "MIGRATE", "PLACE", "SCALE"],
        "physical_actuation": False,
    }


@app.post("/validate")
def validate(req: ValidateRequest) -> dict:
    verdict = gate.evaluate(req.model_dump())
    return {"approved": verdict.approved, "reasons": verdict.reasons}


async def _publish(event: dict) -> dict:
    nats_url = os.getenv("NATS_URL")
    if not nats_url:
        raise RuntimeError("NATS_URL is required for approved decisions")
    import nats

    connection = await nats.connect(nats_url)
    try:
        jetstream = connection.jetstream()
        acknowledgement = await jetstream.publish(
            "dt.decisions.resource", json.dumps(event, allow_nan=False).encode()
        )
        return {"stream": acknowledgement.stream, "sequence": acknowledgement.seq}
    finally:
        await connection.close()


@app.post("/decisions/approve")
async def approve(req: ApproveRequest) -> dict:
    if req.execution_mode != "shadow":
        raise HTTPException(status_code=422, detail="only shadow execution is available")
    if str(req.action.get("type", "")).upper() == "RESOURCE_ADJUST":
        raise HTTPException(status_code=422, detail="RESOURCE_ADJUST is not supported by the Go controller")
    verdict = gate.evaluate(req.model_dump())
    if not verdict.approved:
        raise HTTPException(status_code=422, detail={"approved": False, "reasons": verdict.reasons})
    event = {
        "event_type": "RESOURCE_DECISION",
        "decision_id": req.decision_id,
        "policy_version": req.policy_version,
        "action": req.action,
        "predicted": req.predicted,
        "dt_fidelity": req.dt_fidelity,
        "destination_free_cpu": req.destination_free_cpu,
        "destination_healthy": req.destination_healthy,
        "source_healthy": req.source_healthy,
        "dry_run": True,
        "safety": {"approved": True, "reasons": verdict.reasons},
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    try:
        publish = await _publish(event)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"decision bus unavailable: {exc}") from exc
    if str(req.action.get("type", "")).upper() == "MIGRATE":
        gate.record_migration(str(req.action.get("source", "")))
    return {"approved": True, "execution_mode": "shadow", "event": event, "publish": publish}
