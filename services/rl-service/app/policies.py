"""Policy/model registry metadata (Member-4, Design Sec 56).

Every policy records model_id, version, dataset, hyperparameters, metrics
and git commit so experiments are reproducible (Sec 57).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from typing import Any


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        sha = out.stdout.strip()
        return sha or "unknown"
    except Exception:
        return "unknown"


def policy_record(
    model_id: str,
    version: str,
    dataset: str,
    hyperparameters: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    blob = json.dumps(
        {"model_id": model_id, "version": version, "hyperparameters": hyperparameters},
        sort_keys=True,
    ).encode()
    return {
        "model_id": model_id,
        "version": version,
        "training_dataset": dataset,
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "hyperparameters": hyperparameters,
        "metrics": metrics,
        "git_commit": git_sha(),
        "artifact_hash": hashlib.sha256(blob).hexdigest()[:16],
    }
