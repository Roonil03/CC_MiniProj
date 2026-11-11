"""Digital Twin state model (Member-4, Python side).

Mirrors the Go twin-manager semantics: timestamped node and workload state,
staleness detection, and the fidelity score with autonomy bands. This module
never touches Kubernetes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NodeState:
    node_id: str
    location: str = ""
    cpu_total: float = 8.0
    cpu_used: float = 0.0
    memory_total_mb: float = 16384.0
    memory_used_mb: float = 0.0
    network_in_mbps: float = 0.0
    network_out_mbps: float = 0.0
    latency_to_cloud_ms: float = 0.0
    health: str = "healthy"
    timestamp: datetime = field(default_factory=_utcnow)
    stale: bool = False
    fidelity: float = 0.0

    @property
    def cpu_util(self) -> float:
        return self.cpu_used / self.cpu_total if self.cpu_total > 0 else 0.0

    @property
    def mem_util(self) -> float:
        return self.memory_used_mb / self.memory_total_mb if self.memory_total_mb > 0 else 0.0


@dataclass
class WorkloadState:
    service_id: str
    node_id: str = ""
    replicas: int = 1
    cpu_request: float = 0.5
    memory_request_mb: float = 512.0
    cpu_usage: float = 0.0
    memory_usage_mb: float = 0.0
    request_rate: float = 0.0
    p95_latency_ms: float = 0.0
    slo_ms: float = 50.0


# Weights and normalizers mirror the Go implementation.
_FIDELITY_W = {"cpu": 1.0, "memory": 1.0, "network_in": 0.5, "network_out": 0.5}
_FIDELITY_Z = {"cpu": 1.0, "memory": 1.0, "network_in": 1000.0, "network_out": 1000.0}


def fidelity_score(
    physical_cpu: float,
    physical_mem: float,
    physical_net_in: float,
    physical_net_out: float,
    twin: NodeState,
) -> float:
    """F_t = 1 - sum(w_i * |x_phys - x_twin|) / sum(w_i * Z_i), clamped [0,1]."""
    num = (
        _FIDELITY_W["cpu"] * abs(physical_cpu - twin.cpu_util)
        + _FIDELITY_W["memory"] * abs(physical_mem - twin.mem_util)
        + _FIDELITY_W["network_in"] * abs(physical_net_in - twin.network_in_mbps)
        + _FIDELITY_W["network_out"] * abs(physical_net_out - twin.network_out_mbps)
    )
    den = sum(_FIDELITY_W[k] * _FIDELITY_Z[k] for k in _FIDELITY_W)
    if den <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - num / den))


def autonomy_level(fidelity: float, stale: bool) -> str:
    if stale:
        return "disabled-stale"
    if fidelity > 0.95:
        return "autonomous"
    if fidelity >= 0.90:
        return "restricted"
    if fidelity >= 0.80:
        return "simulation-only"
    return "disabled"


class TwinState:
    """Synchronized virtual infrastructure state (sync pipeline Sec 17)."""

    def __init__(self, stale_after_seconds: float = 5.0) -> None:
        self._nodes: dict[str, NodeState] = {}
        self._workloads: dict[str, WorkloadState] = {}
        self._stale_after = stale_after_seconds

    # -- sync -----------------------------------------------------------
    def apply_telemetry(
        self,
        node_id: str,
        cpu_util: float,
        mem_util: float,
        network_in_mbps: float = 0.0,
        network_out_mbps: float = 0.0,
        cpu_total: float = 8.0,
        memory_total_mb: float = 16384.0,
        health: str = "healthy",
        timestamp: datetime | None = None,
        stale: bool = False,
    ) -> NodeState:
        if not node_id:
            raise ValueError("node_id is required")
        if not 0.0 <= cpu_util <= 1.0:
            raise ValueError(f"cpu utilization must be in [0,1], got {cpu_util}")
        if not 0.0 <= mem_util <= 1.0:
            raise ValueError(f"memory utilization must be in [0,1], got {mem_util}")
        ts = timestamp or _utcnow()
        prev = self._nodes.get(node_id)
        node = NodeState(
            node_id=node_id,
            location=prev.location if prev else "",
            cpu_total=cpu_total,
            cpu_used=cpu_util * cpu_total,
            memory_total_mb=memory_total_mb,
            memory_used_mb=mem_util * memory_total_mb,
            network_in_mbps=network_in_mbps,
            network_out_mbps=network_out_mbps,
            latency_to_cloud_ms=prev.latency_to_cloud_ms if prev else 0.0,
            health=health or "healthy",
            timestamp=ts,
            stale=(stale or ts > _utcnow() or (_utcnow() - ts).total_seconds() > self._stale_after),
        )
        self._nodes[node_id] = node
        return node

    def upsert_workload(self, workload: WorkloadState) -> None:
        if not workload.service_id:
            raise ValueError("service_id is required")
        self._workloads[f"{workload.service_id}/{workload.node_id}"] = workload

    # -- read -----------------------------------------------------------
    def get_node(self, node_id: str) -> NodeState | None:
        return self._nodes.get(node_id)

    def list_nodes(self) -> list[NodeState]:
        return list(self._nodes.values())

    def list_workloads(self) -> list[WorkloadState]:
        return list(self._workloads.values())

    def refresh_staleness(self) -> None:
        now = _utcnow()
        for node in self._nodes.values():
            node.stale = (now - node.timestamp).total_seconds() > self._stale_after

    def score_all(self, physical: dict[str, dict[str, float]]) -> dict[str, float]:
        """Score every node against a physical sample; stores fidelity."""
        out: dict[str, float] = {}
        for node_id, sample in physical.items():
            twin = self._nodes.get(node_id)
            if twin is None:
                continue
            f = fidelity_score(
                sample.get("cpu", 0.0),
                sample.get("memory", 0.0),
                sample.get("network_in", 0.0),
                sample.get("network_out", 0.0),
                twin,
            )
            twin.fidelity = f
            out[node_id] = f
        return out
