"""Opt-in, local-only adversarial fixtures for implemented simulation boundaries."""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "simulation-service"))
sys.path.insert(0, str(ROOT / "services" / "prediction-service"))
from app.safety import GateConfig, SafetyGate  # noqa: E402
from app.simulator import simulate_action  # noqa: E402
from app.twin import TwinState  # noqa: E402
from prediction_app.data import NodeSample, SampleStore  # noqa: E402

SCENARIOS = (
    "burst_memory", "degraded_migration", "telemetry_replay", "store_outage",
    "correlated_failure", "forecast_drift", "conflicting_constraints", "migration_cooldown",
)


def gate_request(confidence: float = 0.99) -> dict:
    return {"action": {"type": "MIGRATE", "source": "edge-a", "destination": "edge-b"},
            "predicted": {"prediction_confidence": confidence, "slo_violation_probability": 0.01},
            "dt_fidelity": 0.99, "source_healthy": True, "destination_healthy": True,
            "destination_free_cpu": 2.0}


def exercise(name: str, seed: int) -> dict:
    rng = random.Random(seed)
    started = time.perf_counter()
    metrics: dict = {}
    status = "simulated"
    expected = "unsafe candidate rejected"
    if name == "burst_memory":
        twin = TwinState()
        twin.apply_telemetry("edge-hot", 0.95, 0.95, cpu_total=8, memory_total_mb=4096)
        twin.apply_telemetry("edge-small", 0.80, 0.90, cpu_total=2, memory_total_mb=1024)
        result = simulate_action(twin, {"type": "PLACE", "destination": "edge-small"},
                                 service_cpu=0.5 + rng.random() * 0.01, service_mem_mb=512)
        metrics = {"feasible": result.feasible, "slo_violation_probability": result.slo_violation_prob,
                   "predicted_latency_ms": result.predicted_latency_ms}
    elif name == "degraded_migration":
        twin = TwinState()
        twin.apply_telemetry("edge-a", 0.6, 0.5)
        twin.apply_telemetry("edge-b", 0.2, 0.2)
        zero = simulate_action(twin, {"type": "MIGRATE", "source": "edge-a", "destination": "edge-b",
                                      "bandwidth_mbps": 0})
        degraded = simulate_action(twin, {"type": "MIGRATE", "source": "edge-a", "destination": "edge-b",
                                          "bandwidth_mbps": 5})
        metrics = {"zero_bandwidth_feasible": zero.feasible, "degraded_feasible": degraded.feasible,
                   "migration_cost": degraded.migration_cost,
                   "migration_duration_s": degraded.migration_duration_s}
    elif name == "telemetry_replay":
        with tempfile.TemporaryDirectory() as temp:
            store = SampleStore(Path(temp) / "fixture.sqlite")
            sample = NodeSample("edge-a", datetime(2025, 1, 1, tzinfo=timezone.utc), 0.0, 0.1, 0.0, 0.0)
            inserted = store.add(sample)
            duplicate = store.add(sample)
            conflict_rejected = False
            try:
                store.add(NodeSample(sample.node_id, sample.timestamp, 0.9, 0.1, 0, 0))
            except ValueError:
                conflict_rejected = True
            store.close()
        metrics = {"zero_inserted": inserted, "duplicate_inserted": duplicate,
                   "conflict_rejected": conflict_rejected}
    elif name == "store_outage":
        # A local fake makes recovery/replay explicit without touching Redis/NATS.
        class FakeStore:
            def __init__(self):
                self.available = False
                self.seen = set()

            def add(self, decision_id):
                if not self.available:
                    raise ConnectionError("synthetic outage")
                before = len(self.seen)
                self.seen.add(decision_id)
                return len(self.seen) != before
        store = FakeStore()
        outage = False
        try:
            store.add("decision-1")
        except ConnectionError:
            outage = True
        store.available = True
        metrics = {"outage_detected": outage, "replay_inserted": store.add("decision-1"),
                   "duplicate_inserted": store.add("decision-1")}
    elif name == "correlated_failure":
        twin = TwinState()
        twin.apply_telemetry("edge-a", 0.4, 0.5, health="failed")
        twin.apply_telemetry("edge-b", 0.3, 0.4, health="failed")
        outcomes = [simulate_action(twin, {"type": "PLACE", "destination": node})
                    for node in ("edge-a", "edge-b")]
        metrics = {"feasible_placements": sum(result.feasible for result in outcomes)}
    elif name == "forecast_drift":
        verdict = SafetyGate().evaluate(gate_request(0.1))
        metrics = {"approved": verdict.approved, "reasons": verdict.reasons}
    elif name == "conflicting_constraints":
        status = "planned"
        expected = "affinity, locality, noisy-neighbour and SLO conflict modelling requires a richer state contract"
        metrics = {"supported": False}
    elif name == "migration_cooldown":
        gate = SafetyGate(GateConfig(max_migrations_per_minute=1))
        first = gate.evaluate(gate_request())
        if first.approved:
            gate.record_migration("edge-a")
        second = gate.evaluate(gate_request())
        metrics = {"first_approved": first.approved, "second_approved": second.approved,
                   "second_reasons": second.reasons}
    else:
        raise ValueError(f"unknown scenario: {name}")
    metrics["decision_latency_ms"] = round((time.perf_counter() - started) * 1000, 6)
    return {"scenario": name, "seed": seed, "status": status,
            "expected_safe_behavior": expected, "metrics": metrics}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.seed < 0:
        parser.error("seed must be nonnegative")
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "synthetic": True,
              "assumptions": "Deterministic local fixtures; no live cluster, network or broker",
              "results": [exercise(name, args.seed) for name in args.scenarios]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
