"""Safety / policy gate (Member-4, Python side).

Explicit checks, not reward shaping: capacity, SLO, health, DT freshness /
fidelity, prediction confidence, migration storm limits and cooldowns
(Design Sec 33-36, AGENTS.md safety boundary). Fail-closed everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class GateConfig:
    min_fidelity: float = 0.80
    min_confidence: float = 0.80
    max_slo_prob: float = 0.10
    max_migrations_per_minute: int = 3
    node_cooldown_seconds: float = 30.0


@dataclass
class Verdict:
    approved: bool
    reasons: list[str] = field(default_factory=list)


class SafetyGate:
    def __init__(self, config: GateConfig | None = None) -> None:
        self.config = config or GateConfig()
        self._migrations: list[datetime] = []
        self._node_last: dict[str, datetime] = {}

    def _prune(self, now: datetime) -> None:
        cutoff = now.timestamp() - 60.0
        self._migrations = [t for t in self._migrations if t.timestamp() > cutoff]

    def evaluate(self, request: dict[str, Any]) -> Verdict:
        reasons: list[str] = []
        action = request.get("action", {})
        atype = str(action.get("type", "NOOP")).upper()
        predicted = request.get("predicted", {})

        if atype == "NOOP":
            return Verdict(True, ["noop always safe"])

        fidelity = float(request.get("dt_fidelity", 0.0))
        if fidelity < self.config.min_fidelity:
            reasons.append(
                f"dt fidelity {fidelity:.3f} below minimum {self.config.min_fidelity:.3f}: disable RL actuation"
            )
        conf = float(predicted.get("prediction_confidence", 0.0) or 0.0)
        if 0.0 < conf < self.config.min_confidence:
            reasons.append(
                f"prediction confidence {conf:.3f} below minimum {self.config.min_confidence:.3f}"
            )
        slo_p = float(predicted.get("slo_violation_probability", 1.0))
        if slo_p > self.config.max_slo_prob:
            reasons.append(
                f"predicted SLO violation probability {slo_p:.3f} exceeds max {self.config.max_slo_prob:.3f}"
            )
        if not request.get("source_healthy", False):
            reasons.append("source node unhealthy")
        if atype in ("MIGRATE", "PLACE"):
            if not request.get("destination_healthy", False):
                reasons.append("destination node unhealthy or unavailable")
            if float(request.get("destination_free_cpu", 0.0)) <= 0:
                reasons.append("destination lacks free capacity")

        if atype == "MIGRATE":
            now = datetime.now(timezone.utc)
            self._prune(now)
            if len(self._migrations) >= self.config.max_migrations_per_minute:
                reasons.append(
                    f"migration storm protection: {len(self._migrations)} in last minute "
                    f"(max {self.config.max_migrations_per_minute})"
                )
            last = self._node_last.get(action.get("source", ""))
            if last is not None:
                elapsed = (now - last).total_seconds()
                if elapsed < self.config.node_cooldown_seconds:
                    reasons.append(
                        f"source node {action.get('source')} in cooldown "
                        f"({self.config.node_cooldown_seconds - elapsed:.0f}s remaining)"
                    )

        if reasons:
            return Verdict(False, reasons)
        return Verdict(True, ["all safety checks passed"])

    def record_migration(self, source: str) -> None:
        now = datetime.now(timezone.utc)
        self._migrations.append(now)
        self._node_last[source] = now
