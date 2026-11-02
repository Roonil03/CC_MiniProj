#!/usr/bin/env python3
"""Synthetic, shadow-only walkthrough of DT-RAM simulation and safety."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import random
import sys


SERVICE_ROOT = Path(__file__).resolve().parents[1] / "services" / "simulation-service"
sys.path.insert(0, str(SERVICE_ROOT))

from app.safety import SafetyGate  # noqa: E402
from app.simulator import evaluate_candidates  # noqa: E402
from app.twin import TwinState  # noqa: E402


def build_demo(seed: int) -> tuple[TwinState, list[dict], list[dict]]:
    rng = random.Random(seed)
    twin = TwinState(stale_after_seconds=30)
    values = {
        "edge-hot": (0.88, 0.62),
        "edge-cool": (0.24, 0.38),
        "edge-stale": (0.42, 0.47),
    }
    now = datetime.now(timezone.utc)
    for node_id, (cpu, memory) in values.items():
        # Small deterministic variation makes --seed useful while keeping the
        # fixture's hot/cool/stale roles clear.
        cpu = round(cpu + rng.uniform(-0.015, 0.015), 3)
        memory = round(memory + rng.uniform(-0.015, 0.015), 3)
        timestamp = now - timedelta(minutes=3) if node_id == "edge-stale" else now
        twin.apply_telemetry(
            node_id,
            cpu,
            memory,
            network_in_mbps=18.0,
            network_out_mbps=12.0,
            timestamp=timestamp,
        )
    # Independent synthetic comparison samples: intentionally close to, but
    # not copied from, the twin telemetry so the fidelity score is meaningful.
    physical_samples = {
        "edge-hot": {"cpu": 0.90, "memory": 0.60, "network_in": 20.0, "network_out": 11.0},
        "edge-cool": {"cpu": 0.26, "memory": 0.40, "network_in": 16.0, "network_out": 13.0},
        "edge-stale": {"cpu": 0.40, "memory": 0.49, "network_in": 19.0, "network_out": 10.0},
    }
    twin.score_all(physical_samples)
    actions = [
        {"type": "NOOP", "source": "edge-hot", "label": "Keep current placement"},
        {"type": "SCALE", "source": "edge-hot", "replicas": 3, "label": "Scale hot service to 3"},
        {
            "type": "MIGRATE",
            "source": "edge-hot",
            "destination": "edge-cool",
            "label": "Migrate hot -> cool",
        },
        {
            "type": "MIGRATE",
            "source": "edge-hot",
            "destination": "edge-stale",
            "label": "Migrate hot -> stale",
        },
    ]
    results = evaluate_candidates(
        twin,
        actions,
        service_cpu=0.6,
        service_mem_mb=768.0,
        service_rate=120.0,
        state_mb=128.0,
        bandwidth_mbps=200.0,
    )
    return twin, actions, results


def _verdicts(twin: TwinState, actions: list[dict], results: list) -> list[dict]:
    gate = SafetyGate()
    verdicts = []
    for action, result in zip(actions, results):
        if not result.feasible:
            verdicts.append({"approved": False, "reasons": ["counterfactual simulation is infeasible"]})
            continue
        source = twin.get_node(action.get("source", ""))
        destination = twin.get_node(action.get("destination", ""))
        # The gate's fidelity threshold is the available freshness/fidelity
        # control. A stale node is represented as zero fidelity for this check.
        fidelity = min(
            (source.fidelity if source and not source.stale else 0.0),
            (destination.fidelity if destination and not destination.stale else 1.0),
        )
        if (source and source.stale) or (destination and destination.stale):
            fidelity = 0.0
        verdict = gate.evaluate(
            {
                "action": action,
                "predicted": {
                    "slo_violation_probability": result.slo_violation_prob,
                    "prediction_confidence": 0.92,
                },
                "dt_fidelity": fidelity,
                "source_healthy": bool(source and source.health == "healthy" and not source.stale),
                "destination_healthy": bool(destination and destination.health == "healthy" and not destination.stale),
                "destination_free_cpu": (destination.cpu_total - destination.cpu_used) if destination else 0,
            }
        )
        verdicts.append({"approved": verdict.approved, "reasons": verdict.reasons})
    return verdicts


def _colored(text: str, code: str, enabled: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if enabled else text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42, help="deterministic synthetic fixture seed (default: 42)")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("--json", action="store_true", help="print results as JSON")
    args = parser.parse_args()
    color = not args.no_color and "NO_COLOR" not in os.environ and sys.stdout.isatty()

    twin, actions, results = build_demo(args.seed)
    verdicts = _verdicts(twin, actions, results)
    if args.json:
        print(
            json.dumps(
                {
                    "mode": "shadow-only",
                    "seed": args.seed,
                    "nodes": [
                        {
                            "id": n.node_id,
                            "cpu_pct": round(n.cpu_util * 100, 1),
                            "memory_pct": round(n.mem_util * 100, 1),
                            "fidelity": round(n.fidelity if not n.stale else 0.0, 3),
                            "stale": n.stale,
                        }
                        for n in twin.list_nodes()
                    ],
                    "candidates": [
                        {
                            "action": action["label"],
                            "simulation": {
                                "feasible": result.feasible,
                                "cpu_pct": round(result.predicted_cpu * 100, 1),
                                "memory_pct": round(result.predicted_mem * 100, 1),
                                "latency_ms": round(result.predicted_latency_ms, 1),
                                "slo_violation_probability": round(result.slo_violation_prob, 4),
                                "migration_cost": round(result.migration_cost, 3),
                                "migration_duration_s": round(result.migration_duration_s, 2),
                            },
                            "safety": verdict,
                        }
                        for action, result, verdict in zip(actions, results, verdicts)
                    ],
                },
                indent=2,
            )
        )
        return 0

    badge = _colored(" SHADOW-ONLY | NO ACTUATION ", "1;37;41", color)
    print(f"DT-RAM  {badge}  synthetic demo | seed {args.seed}")
    print("Candidate actions are simulated and checked; none are sent to infrastructure.\n")
    print("DIGITAL TWIN (synthetic fixture; fidelity compared with independent synthetic samples)")
    print(f"{'NODE':<14} {'CPU':>7} {'MEM':>7} {'FIDELITY':>10}  STATUS")
    for node in twin.list_nodes():
        status = "STALE - fail closed" if node.stale else ("HOT" if node.node_id == "edge-hot" else "healthy")
        status = _colored(status, "1;33" if node.stale or node.node_id == "edge-hot" else "32", color)
        effective_fidelity = node.fidelity if not node.stale else 0.0
        print(f"{node.node_id:<14} {node.cpu_util:>6.1%} {node.mem_util:>6.1%} {effective_fidelity:>10.3f}  {status}")

    print("\nCOUNTERFACTUALS -> SAFETY GATE")
    print(f"{'CANDIDATE':<27} {'SIM':<9} {'CPU':>6} {'MEM':>6} {'P95*':>7} {'SLO P':>7} {'MIG COST':>9} {'GATE':<10}")
    for action, result, verdict in zip(actions, results, verdicts):
        sim = "feasible" if result.feasible else "blocked"
        gate = "APPROVED" if verdict["approved"] else "DENIED"
        gate = _colored(gate, "32" if verdict["approved"] else "1;31", color)
        print(
            f"{action['label']:<27} {sim:<9} {result.predicted_cpu:>5.1%} "
            f"{result.predicted_mem:>5.1%} {result.predicted_latency_ms:>6.1f} "
            f"{result.slo_violation_prob:>6.1%} {result.migration_cost:>9.2f} {gate}"
        )
        if not verdict["approved"]:
            for reason in verdict["reasons"]:
                print(f"  - {reason}")
        elif result.action_type == "MIGRATE":
            print(f"  - migration duration: {result.migration_duration_s:.2f}s")
    print("\n* Simulator latency estimate. Safety verdicts are illustrative; this demo is shadow-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
