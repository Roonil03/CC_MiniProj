#!/usr/bin/env python3
"""Read-only Kubernetes or synthetic shadow-only DT-RAM simulation walkthrough."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time


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


def _kubectl_json(args: list[str], kubeconfig: str | None) -> dict:
    command = ["kubectl"]
    if kubeconfig:
        command.extend(["--kubeconfig", kubeconfig])
    command.extend(args)
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("kubectl was not found; install it and ensure it is on PATH") from exc
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown kubectl error"
        raise RuntimeError(f"{' '.join(command)} failed: {detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"kubectl returned invalid JSON for {' '.join(args)}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"kubectl returned an unexpected response for {' '.join(args)}")
    return value


def _quantity(value: str, *, cpu: bool) -> float:
    """Convert a Kubernetes CPU quantity to cores or memory quantity to bytes."""
    match = re.fullmatch(
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]*)", str(value)
    )
    if not match:
        raise ValueError(f"unsupported Kubernetes quantity: {value!r}")
    number = float(match.group(1))
    suffix = match.group(2)
    if cpu:
        factors = {"": 1.0, "n": 1e-9, "u": 1e-6, "m": 1e-3}
        if suffix not in factors:
            raise ValueError(f"unsupported CPU quantity suffix: {suffix!r}")
        return number * factors[suffix]
    factors = {
        "": 1.0,
        "k": 1e3,
        "K": 1e3,
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
        "P": 1e15,
        "E": 1e18,
        "Ki": 1024.0,
        "Mi": 1024.0**2,
        "Gi": 1024.0**3,
        "Ti": 1024.0**4,
        "Pi": 1024.0**5,
        "Ei": 1024.0**6,
    }
    if suffix not in factors:
        raise ValueError(f"unsupported memory quantity suffix: {suffix!r}")
    return number * factors[suffix]


def build_cluster_demo(kubeconfig: str | None) -> tuple[TwinState, list[dict], list[dict], str]:
    """Read Node and metrics.k8s.io APIs through kubectl; never writes to Kubernetes."""
    nodes_response = _kubectl_json(["get", "nodes", "-o", "json"], kubeconfig)
    node_items = nodes_response.get("items", [])
    if not node_items:
        raise RuntimeError("the Kubernetes API returned no nodes")
    for attempt in range(12):
        try:
            metrics_response = _kubectl_json(["get", "--raw", "/apis/metrics.k8s.io/v1beta1/nodes"], kubeconfig)
            metrics_by_name = {
                item.get("metadata", {}).get("name"): item
                for item in metrics_response.get("items", [])
            }
            missing = [
                item.get("metadata", {}).get("name", "<unnamed>")
                for item in node_items
                if item.get("metadata", {}).get("name") not in metrics_by_name
            ]
            if not missing:
                break
            detail = "metrics.k8s.io has no usage sample for node(s): " + ", ".join(missing)
        except RuntimeError as exc:
            detail = str(exc)
            if "ServiceUnavailable" not in detail and "server is currently unable" not in detail:
                raise
        if attempt == 11:
            raise RuntimeError(detail + "; ensure metrics-server is running and retry")
        time.sleep(5)
    try:
        context_response = subprocess.run(
        [
            "kubectl",
            *( ["--kubeconfig", kubeconfig] if kubeconfig else [] ),
            "config",
            "current-context",
        ],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("kubectl was not found; install it and ensure it is on PATH") from exc
    context = context_response.stdout.strip() if context_response.returncode == 0 else "current context"
    twin = TwinState(stale_after_seconds=120.0)
    for item in node_items:
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        if not name:
            continue
        status = item.get("status", {})
        allocatable = status.get("allocatable", {})
        capacity = status.get("capacity", {})
        cpu_total = _quantity(allocatable.get("cpu", capacity.get("cpu", "0")), cpu=True)
        mem_total_mb = (
            _quantity(allocatable.get("memory", capacity.get("memory", "0")), cpu=False)
            / (1024.0**2)
        )
        metric = metrics_by_name[name]
        usage = metric.get("usage", {})
        cpu_used = _quantity(usage.get("cpu", "0"), cpu=True)
        mem_used_mb = _quantity(usage.get("memory", "0"), cpu=False) / (1024.0**2)
        timestamp_text = metric.get("timestamp")
        if not timestamp_text:
            raise RuntimeError(f"metrics.k8s.io sample for node {name} has no timestamp")
        try:
            timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise RuntimeError(f"invalid metrics timestamp for node {name}: {timestamp_text!r}") from exc
        conditions = status.get("conditions", [])
        ready = next((condition for condition in conditions if condition.get("type") == "Ready"), None)
        health = "healthy" if ready and ready.get("status") == "True" else "unhealthy"
        if cpu_total <= 0 or mem_total_mb <= 0:
            raise RuntimeError(f"node {name} has invalid allocatable CPU or memory")
        twin.apply_telemetry(
            name,
            min(1.0, cpu_used / cpu_total),
            min(1.0, mem_used_mb / mem_total_mb),
            cpu_total=cpu_total,
            memory_total_mb=mem_total_mb,
            health=health,
            timestamp=timestamp,
        )

    healthy = [node for node in twin.list_nodes() if node.health == "healthy" and not node.stale]
    source = max(healthy or twin.list_nodes(), key=lambda node: node.cpu_util)
    destinations = [node for node in healthy if node.node_id != source.node_id]
    actions = [{"type": "NOOP", "source": source.node_id, "label": "Keep current placement"}]
    actions.append(
        {
            "type": "SCALE",
            "source": source.node_id,
            "replicas": 3,
            "label": "Scale illustrative service to 3",
        }
    )
    if destinations:
        destination = min(destinations, key=lambda node: node.cpu_util)
        actions.append({
            "type": "MIGRATE", "source": source.node_id, "destination": destination.node_id,
            "label": f"Migrate illustrative service -> {destination.node_id}",
        })
    results = evaluate_candidates(
        twin,
        actions,
        service_cpu=0.6,
        service_mem_mb=768.0,
        service_rate=120.0,
        state_mb=128.0,
        bandwidth_mbps=200.0,
    )
    # No independent, scope-matched reference stream is available. Leave fidelity
    # at zero so the safety gate fails closed for non-NOOP actions.
    return twin, actions, results, context


def _verdicts(
    twin: TwinState, actions: list[dict], results: list, prediction_confidence: float = 0.92
) -> list[dict]:
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
                    "prediction_confidence": prediction_confidence,
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
    parser.add_argument("--kubeconfig", help="kubeconfig path (otherwise kubectl uses KUBECONFIG/current context)")
    parser.add_argument("--synthetic", action="store_true", help="use the built-in synthetic fixture instead of Kubernetes")
    parser.add_argument("--seed", type=int, default=42, help="synthetic fixture seed (default: 42)")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("--json", action="store_true", help="print results as JSON")
    args = parser.parse_args()
    color = not args.no_color and "NO_COLOR" not in os.environ and sys.stdout.isatty()

    if args.synthetic:
        twin, actions, results = build_demo(args.seed)
        mode = "synthetic"
        context = None
    else:
        try:
            twin, actions, results, context = build_cluster_demo(args.kubeconfig)
        except (RuntimeError, ValueError) as exc:
            print(f"DT-RAM Kubernetes snapshot failed: {exc}", file=sys.stderr)
            return 2
        mode = "kubernetes"
    verdicts = _verdicts(
        twin, actions, results, prediction_confidence=0.0 if mode == "kubernetes" else 0.92
    )
    if args.json:
        print(
            json.dumps(
                {
                    "mode": "shadow-only",
                    "source": mode,
                    "context": context,
                    "seed": args.seed if args.synthetic else None,
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
                    "fidelity_note": (
                        "No independent, scope-matched reference stream is available; fidelity is zero, "
                        "and no measured prediction confidence is available, so the safety gate fails "
                        "closed for non-NOOP actions."
                        if mode == "kubernetes" else None
                    ),
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
    source_label = (
        f"Kubernetes snapshot | context {context}"
        if mode == "kubernetes"
        else f"synthetic demo | seed {args.seed}"
    )
    print(f"DT-RAM  {badge}  {source_label}")
    print("Candidate actions are simulated and checked; none are sent to infrastructure.\n")
    if mode == "kubernetes":
        print("DIGITAL TWIN (read-only Node API + metrics.k8s.io snapshot)")
        print("Network metrics and model confidence are unavailable; fidelity/confidence are 0.")
        print("The safety gate therefore fails closed for non-NOOP actions.")
    else:
        print("DIGITAL TWIN (synthetic fixture; fidelity compared with independent synthetic samples)")
    node_width = max(14, *(len(node.node_id) for node in twin.list_nodes()))
    print(f"{'NODE':<{node_width}} {'CPU':>7} {'MEM':>7} {'FIDELITY':>10}  STATUS")
    for node in twin.list_nodes():
        status = "STALE - fail closed" if node.stale else ("NOT READY" if node.health != "healthy" else "healthy")
        if mode == "synthetic" and node.node_id == "edge-hot" and not node.stale:
            status = "HOT"
        status = _colored(status, "1;33" if node.stale or node.health != "healthy" or status == "HOT" else "32", color)
        effective_fidelity = node.fidelity if not node.stale else 0.0
        print(f"{node.node_id:<{node_width}} {node.cpu_util:>6.1%} {node.mem_util:>6.1%} {effective_fidelity:>10.3f}  {status}")

    print("\nCOUNTERFACTUALS -> SAFETY GATE")
    candidate_width = max(27, *(len(action["label"]) for action in actions))
    print(f"{'CANDIDATE':<{candidate_width}} {'SIM':<9} {'CPU':>6} {'MEM':>6} {'P95*':>7} {'SLO P':>7} {'MIG COST':>9} {'GATE':<10}")
    for action, result, verdict in zip(actions, results, verdicts):
        sim = "feasible" if result.feasible else "blocked"
        gate = "APPROVED" if verdict["approved"] else "DENIED"
        gate = _colored(gate, "32" if verdict["approved"] else "1;31", color)
        print(
            f"{action['label']:<{candidate_width}} {sim:<9} {result.predicted_cpu:>5.1%} "
            f"{result.predicted_mem:>5.1%} {result.predicted_latency_ms:>6.1f} "
            f"{result.slo_violation_prob:>6.1%} {result.migration_cost:>9.2f} {gate}"
        )
        if not verdict["approved"]:
            for reason in verdict["reasons"]:
                print(f"  - {reason}")
        elif result.action_type == "MIGRATE":
            print(f"  - migration duration: {result.migration_duration_s:.2f}s")
    if mode == "kubernetes":
        print("\n* CPU/memory are live metrics-server node samples. Candidate workload size and latency are illustrative.")
        print("  Safety verdicts are shadow-only; no Kubernetes resources are changed.")
    else:
        print("\n* Simulator latency estimate. Safety verdicts are illustrative; this demo is shadow-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
