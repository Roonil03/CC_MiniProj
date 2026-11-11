"""Local model metadata and explicit serving selection."""

from __future__ import annotations

import argparse
import hashlib
import os
import json
from pathlib import Path

from .models import Scale, neural_network


class Registry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.active_path = self.path.with_name("active.json")

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise ValueError("registry must be a list")
        return value

    def active(self) -> dict[str, str]:
        if not self.active_path.exists():
            return {}
        value = json.loads(self.active_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("active model mapping must be an object")
        return value

    def activate(self, model_id: str) -> dict:
        record = next((r for r in self.records() if r["model_id"] == model_id), None)
        if record is None:
            raise ValueError("model_id not found")
        if record["kind"] in ("arima", "ets"):
            raise ValueError("per-request statistical refits cannot be served")
        if record["kind"] != "persistence":
            self.load_network(record)  # verify artifact before activation
        active = self.active()
        active[record["metric"]] = model_id
        self.active_path.write_text(json.dumps(active, indent=2), encoding="utf-8")
        return record

    def selected(self, metric: str) -> dict | None:
        model_id = self.active().get(metric)
        if model_id is None:
            return None
        record = next((r for r in self.records() if r["model_id"] == model_id), None)
        if record is None:
            raise ValueError(f"active model {model_id} is absent")
        if record.get("metric") != metric:
            raise ValueError(f"active model {model_id} targets a different metric")
        return record

    def load_network(self, record: dict):
        import torch

        name = record.get("weights_file")
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("invalid weights filename")
        artifact = self.path.parent / name
        content_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if content_hash != record.get("artifact_hash"):
            raise ValueError("artifact hash mismatch")
        config = record["hyperparameters"]
        require_cuda = os.getenv("DT_RAM_REQUIRE_CUDA") == "1"
        if require_cuda and not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU required for prediction but unavailable")
        device = torch.device("cuda" if require_cuda else "cpu")
        network = neural_network(record["kind"], config["history_steps"],
                                 len(config["horizons_seconds"])).to(device)
        network.load_state_dict(torch.load(artifact, map_location="cpu", weights_only=True))
        scale = Scale(**record["scale"])
        return network, scale


def main() -> None:
    parser = argparse.ArgumentParser(description="Activate a reviewed forecast model")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--model-id", required=True)
    args = parser.parse_args()
    record = Registry(args.registry).activate(args.model_id)
    print(json.dumps({"active": record["model_id"], "metric": record["metric"]}))


if __name__ == "__main__":
    main()
