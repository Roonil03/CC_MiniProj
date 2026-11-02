"""Counterfactual simulator (Member-4).

Answers "what is likely to happen if this action is taken?" for candidate
actions (no-op, migrate, scale, place, resource-adjust) against the twin
state. Models resource, workload/queueing, network and migration dynamics
(resource, queueing, network, and migration dynamics). A simulated action is
an evaluation result — never a
permission to touch Kubernetes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .twin import TwinState


@dataclass
class SimResult:
    action_type: str
    predicted_cpu: float
    predicted_mem: float
    predicted_latency_ms: float
    slo_violation_prob: float
    migration_cost: float
    migration_duration_s: float
    feasible: bool
    notes: list[str]


def migration_duration(state_mb: float, bandwidth_mbps: float, overhead_s: float = 2.0) -> float:
    """First-order estimate: T = S_state/B_effective + T_overhead."""
    if bandwidth_mbps <= 0:
        return -1.0
    return (state_mb * 8.0 / bandwidth_mbps) + overhead_s


def migration_cost(
    state_mb: float = 100.0,
    bandwidth_mbps: float = 200.0,
    downtime_s: float = 1.0,
    w_net: float = 1.0,
    w_cpu: float = 0.5,
    w_downtime: float = 2.5,
) -> float:
    """Migration is not free: C_network + C_cpu + C_downtime + C_state."""
    transfer_s = state_mb * 8.0 / bandwidth_mbps if bandwidth_mbps > 0 else float("inf")
    return w_net * transfer_s + w_cpu * (state_mb / 1024.0) + w_downtime * downtime_s


def _latency_model(cpu_util: float, base_ms: float = 8.0, steepness: float = 6.0) -> float:
    """Queueing-style latency: flat at low load, steep near saturation."""
    cpu_util = max(0.0, min(1.0, cpu_util))
    return base_ms * (1.0 + steepness * cpu_util**3)


def _slo_prob(latency_ms: float, slo_ms: float, spread: float = 8.0) -> float:
    """Logistic SLO-violation probability around the SLO threshold."""
    import math

    if spread <= 0:
        return 1.0 if latency_ms > slo_ms else 0.0
    return 1.0 / (1.0 + math.exp(-(latency_ms - slo_ms) / spread))


def simulate_action(
    twin: TwinState,
    action: dict[str, Any],
    service_cpu: float = 0.5,
    service_mem_mb: float = 512.0,
    service_rate: float = 100.0,
    state_mb: float = 100.0,
    bandwidth_mbps: float = 200.0,
) -> SimResult:
    """Simulate one candidate action against current twin state."""
    notes: list[str] = []
    atype = str(action.get("type", "NOOP")).upper()
    src = twin.get_node(action.get("source", ""))
    dst = twin.get_node(action.get("destination", ""))

    if atype == "NOOP":
        if src is None:
            return SimResult(atype, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, ["unknown source node"])
        lat = _latency_model(src.cpu_util)
        return SimResult(atype, src.cpu_util, src.mem_util, lat, _slo_prob(lat, 50.0), 0.0, 0.0, True, ["baseline"])

    if atype in ("MIGRATE", "PLACE"):
        if dst is None:
            return SimResult(atype, 0.0, 0.0, 0.0, 1.0, 0.0, -1.0, False, ["unknown destination"])
        if dst.health != "healthy":
            notes.append("destination unhealthy")
            return SimResult(atype, 0.0, 0.0, 0.0, 1.0, 0.0, -1.0, False, notes)
        new_cpu = dst.cpu_util + service_cpu / max(dst.cpu_total, 1e-9)
        new_mem = dst.mem_util + service_mem_mb / max(dst.memory_total_mb, 1e-9)
        if new_cpu > 1.0 or new_mem > 1.0:
            notes.append("destination lacks capacity")
            return SimResult(atype, new_cpu, new_mem, 0.0, 1.0, 0.0, -1.0, False, notes)
        cost = migration_cost(state_mb, bandwidth_mbps) if atype == "MIGRATE" else 0.0
        dur = migration_duration(state_mb, bandwidth_mbps) if atype == "MIGRATE" else 0.0
        lat = _latency_model(new_cpu)
        notes.append(f"scheduler follows approved placement {action.get('source')} -> {dst.node_id}")
        return SimResult(atype, new_cpu, new_mem, lat, _slo_prob(lat, 50.0), cost, dur, True, notes)

    if atype == "SCALE":
        replicas = int(action.get("replicas", 1) or 1)
        per_replica = service_rate / max(replicas, 1)
        # More replicas spread load: effective cpu falls with replica count.
        eff_cpu = (src.cpu_util if src else 0.7) * (1.0 / max(replicas, 1) + 0.5)
        lat = _latency_model(eff_cpu)
        notes.append(f"{replicas} replicas, ~{per_replica:.1f} req/s each")
        return SimResult(atype, eff_cpu, src.mem_util if src else 0.5, lat, _slo_prob(lat, 50.0), 0.0, 0.0, True, notes)

    if atype == "RESOURCE_ADJUST":
        base = src.cpu_util if src else 0.7
        new_cpu = max(0.0, min(1.0, base + float(action.get("cpu_delta", 0.0))))
        lat = _latency_model(new_cpu)
        return SimResult(atype, new_cpu, src.mem_util if src else 0.5, lat, _slo_prob(lat, 50.0), 0.0, 0.0, True, ["vertical adjustment"])

    return SimResult(atype, 0.0, 0.0, 0.0, 1.0, 0.0, -1.0, False, [f"unsupported action {atype}"])


def evaluate_candidates(
    twin: TwinState,
    candidates: list[dict[str, Any]],
    **kwargs: Any,
) -> list[SimResult]:
    return [simulate_action(twin, c, **kwargs) for c in candidates]
