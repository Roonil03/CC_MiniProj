"""Safety-service HTTP stub (Member-2 + Member-4 shared).

Thin FastAPI gate on SAFETY_SERVICE_PORT=5003. Reuses the canonical gate
logic owned by simulation-service; thresholds stay in one place.
"""

from __future__ import annotations

import os
import sys
import json
import threading
import uuid
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
    decision_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    execution_mode: str = "shadow"


gate = SafetyGate(GateConfig())
# SafetyGate keeps process-local migration accounting. Serialize gate access and
# reserve a slot before publishing so concurrent approvals cannot all pass the
# same remaining migration budget.
_approval_lock = threading.Lock()
_pending_migrations: dict[str, tuple[datetime, str]] = {}
_decision_results: dict[str, tuple[datetime, str, dict | None]] = {}


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
    with _approval_lock:
        verdict = gate.evaluate(req.model_dump())
    reasons = list(verdict.reasons)
    shape_error = _action_error(req.action)
    if shape_error:
        reasons.append(shape_error)
    return {"approved": verdict.approved and not shape_error, "reasons": reasons}


def _action_error(action: dict) -> str | None:
    raw_type = action.get("type")
    if not isinstance(raw_type, str) or not raw_type.strip():
        return "action type is required"
    action_type = raw_type.upper()
    if action_type not in {"NOOP", "MIGRATE", "PLACE", "SCALE"}:
        return "unsupported action"
    if action_type == "NOOP":
        return None
    if not str(action.get("service", "")).strip():
        return "service is required"
    if action_type in {"MIGRATE", "PLACE"}:
        destination = str(action.get("destination", "")).strip()
        source = str(action.get("source", "")).strip()
        if action_type == "MIGRATE" and not source:
            return "source is required for MIGRATE"
        if not destination:
            return f"destination is required for {action_type}"
        if source and source == destination:
            return "source and destination must differ"
    if action_type == "SCALE":
        replicas = action.get("replicas")
        if isinstance(replicas, bool) or not isinstance(replicas, int) or replicas < 0:
            return "replicas must be a nonnegative integer for SCALE"
    return None


async def _publish(event: dict) -> dict:
    nats_url = os.getenv("NATS_URL")
    if not nats_url:
        raise RuntimeError("NATS_URL is required for approved decisions")
    import nats

    connection = await nats.connect(nats_url)
    try:
        jetstream = connection.jetstream()
        acknowledgement = await jetstream.publish(
            "dt.decisions.resource", json.dumps(event, allow_nan=False).encode(),
            headers={"Nats-Msg-Id": event["decision_id"]},
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
    shape_error = _action_error(req.action)
    if shape_error:
        raise HTTPException(status_code=422, detail=shape_error)
    action_type = str(req.action.get("type", "")).upper()
    fingerprint = json.dumps(req.model_dump(exclude={"decision_id"}), sort_keys=True, default=str)
    reservation = None
    with _approval_lock:
        now = datetime.now(timezone.utc)
        for key, (created, _, _) in list(_decision_results.items()):
            if (now - created).total_seconds() > 3600:
                _decision_results.pop(key, None)
        previous = _decision_results.get(req.decision_id)
        if previous is not None:
            if previous[1] != fingerprint:
                raise HTTPException(status_code=409, detail="decision ID reused with different inputs")
            if previous[2] is None:
                raise HTTPException(status_code=409, detail="decision publication already pending")
            return previous[2]
        if len(_decision_results) >= 1024:
            for key, (_, _, result) in list(_decision_results.items()):
                if result is not None:
                    _decision_results.pop(key, None)
                    break
            if len(_decision_results) >= 1024:
                raise HTTPException(status_code=503, detail="decision reservation capacity exhausted")
        verdict = gate.evaluate(req.model_dump())
        reasons = list(verdict.reasons)
        if action_type == "MIGRATE":
            now = datetime.now(timezone.utc)
            cutoff = now.timestamp() - 60.0
            for key, (created, _) in list(_pending_migrations.items()):
                if created.timestamp() <= cutoff:
                    _pending_migrations.pop(key, None)
            source = str(req.action.get("source", ""))
            active = sum(created.timestamp() > cutoff for created, _ in _pending_migrations.values())
            if active + len(gate._migrations) >= gate.config.max_migrations_per_minute:
                reasons.append("migration storm protection: pending approvals consume remaining migration budget")
            if any(pending_source == source for _, pending_source in _pending_migrations.values()):
                reasons.append(f"source node {source} already has a pending migration approval")
            if not reasons:
                reservation = str(uuid.uuid4())
                _pending_migrations[reservation] = (now, source)
        if reasons:
            raise HTTPException(status_code=422, detail={"approved": False, "reasons": reasons})
        _decision_results[req.decision_id] = (now, fingerprint, None)
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
        with _approval_lock:
            _decision_results.pop(req.decision_id, None)
            if reservation:
                _pending_migrations.pop(reservation, None)
                # A lost JetStream acknowledgement may follow a successful
                # publish. Count the attempt conservatively to avoid allowing
                # a second migration during that uncertain outcome.
                gate.record_migration(str(req.action.get("source", "")))
        raise HTTPException(status_code=503, detail=f"decision bus unavailable: {exc}") from exc
    response = {"approved": True, "execution_mode": "shadow", "event": event, "publish": publish}
    with _approval_lock:
        if reservation:
            _pending_migrations.pop(reservation, None)
            gate.record_migration(str(req.action.get("source", "")))
        _decision_results[req.decision_id] = (datetime.now(timezone.utc), fingerprint, response)
    return response
