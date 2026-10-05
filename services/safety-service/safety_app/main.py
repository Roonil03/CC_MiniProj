"""Safety-service HTTP stub (Member-2 + Member-4 shared).

Thin FastAPI gate on SAFETY_SERVICE_PORT=5003. Reuses the canonical gate
logic owned by simulation-service; thresholds stay in one place.
"""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI
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


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "safety-service"}


@app.post("/validate")
def validate(req: ValidateRequest) -> dict:
    gate = SafetyGate(GateConfig())
    verdict = gate.evaluate(req.model_dump())
    return {"approved": verdict.approved, "reasons": verdict.reasons}
