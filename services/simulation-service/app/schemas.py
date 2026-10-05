"""DT-RAM simulation-service shared schemas.

Event/contract shapes follow Design.md Sections 16 (node/workload state),
53 (NODE_METRIC_UPDATED) and 54 (RESOURCE_DECISION). Field names are stable
contracts shared with the Go twin-manager / infrastructure-controller.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def node_state(
    node_id: str,
    cpu_total: float = 8.0,
    cpu_used: float = 0.0,
    memory_total_mb: float = 16384.0,
    memory_used_mb: float = 0.0,
    network_in_mbps: float = 0.0,
    network_out_mbps: float = 0.0,
    latency_to_cloud_ms: float = 0.0,
    health: str = "healthy",
    location: str = "",
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "location": location,
        "cpu_total": cpu_total,
        "cpu_used": cpu_used,
        "memory_total_mb": memory_total_mb,
        "memory_used_mb": memory_used_mb,
        "network_in_mbps": network_in_mbps,
        "network_out_mbps": network_out_mbps,
        "latency_to_cloud_ms": latency_to_cloud_ms,
        "health": health,
        "timestamp": (timestamp or utcnow()).isoformat(),
    }


def workload_state(
    service_id: str,
    node_id: str = "",
    replicas: int = 1,
    cpu_request: float = 0.5,
    memory_request_mb: float = 512.0,
    cpu_usage: float = 0.0,
    memory_usage_mb: float = 0.0,
    request_rate: float = 0.0,
    p95_latency_ms: float = 0.0,
    slo_ms: float = 50.0,
) -> dict[str, Any]:
    return {
        "service_id": service_id,
        "node_id": node_id,
        "replicas": replicas,
        "cpu_request": cpu_request,
        "memory_request_mb": memory_request_mb,
        "cpu_usage": cpu_usage,
        "memory_usage_mb": memory_usage_mb,
        "request_rate": request_rate,
        "p95_latency_ms": p95_latency_ms,
        "slo_ms": slo_ms,
    }


def resource_decision(
    decision_id: str,
    policy_version: str,
    action: dict[str, Any],
    predicted: dict[str, Any],
    approved: bool,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Build a Section-54 RESOURCE_DECISION event (propose-only payload)."""
    return {
        "event_type": "RESOURCE_DECISION",
        "decision_id": decision_id,
        "policy_version": policy_version,
        "action": action,
        "predicted": predicted,
        "safety": {"approved": approved},
        "timestamp": (timestamp or utcnow()).isoformat(),
    }


ActionType = Literal["NOOP", "MIGRATE", "SCALE", "PLACE", "RESOURCE_ADJUST"]
