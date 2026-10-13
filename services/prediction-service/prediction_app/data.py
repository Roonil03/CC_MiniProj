"""Validated node telemetry and a restart-safe local recording store.

The implemented Go producer emits NODE_METRIC_UPDATED on
dt.telemetry.node_metric. This module deliberately does not infer application
latency, request rate, or queue length from node telemetry.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

METRICS = ("cpu", "memory", "network_in", "network_out")


def parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an RFC3339 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must contain a timezone")
    return parsed.astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class NodeSample:
    node_id: str
    timestamp: datetime
    cpu: float
    memory: float
    network_in: float
    network_out: float

    @classmethod
    def from_event(cls, event: dict) -> "NodeSample":
        if not isinstance(event, dict) or event.get("event_type") != "NODE_METRIC_UPDATED":
            raise ValueError("expected NODE_METRIC_UPDATED event")
        node_id = event.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id is required")
        metrics = event.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("metrics object is required")
        values = {}
        for name in METRICS:
            raw = metrics.get(name)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"{name} must be numeric")
            value = float(raw)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
            if name in ("cpu", "memory") and value > 1:
                raise ValueError(f"{name} must be a utilization fraction")
            values[name] = value
        return cls(node_id.strip(), parse_time(event.get("timestamp")), **values)

    def to_dict(self) -> dict:
        return {"node_id": self.node_id, "timestamp": format_time(self.timestamp),
                **{name: getattr(self, name) for name in METRICS}}

    def to_event(self) -> dict:
        return {"event_type": "NODE_METRIC_UPDATED", "node_id": self.node_id,
                "timestamp": format_time(self.timestamp),
                "metrics": {name: getattr(self, name) for name in METRICS}}


class SampleStore:
    """SQLite recording store. A successful add is committed before NATS ack."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS node_samples (
            node_id TEXT NOT NULL, timestamp TEXT NOT NULL,
            cpu REAL NOT NULL, memory REAL NOT NULL,
            network_in REAL NOT NULL, network_out REAL NOT NULL,
            PRIMARY KEY(node_id, timestamp))""")
        self.db.commit()

    def add(self, sample: NodeSample) -> bool:
        row = (sample.node_id, format_time(sample.timestamp), sample.cpu,
               sample.memory, sample.network_in, sample.network_out)
        with self.db:
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO node_samples VALUES (?, ?, ?, ?, ?, ?)", row)
            if cursor.rowcount == 0:
                existing = self.db.execute(
                    "SELECT cpu, memory, network_in, network_out FROM node_samples "
                    "WHERE node_id = ? AND timestamp = ?", row[:2]).fetchone()
                if existing != row[2:]:
                    raise ValueError("conflicting sample for node and timestamp")
                return False
        return True

    def samples(self, node_id: str | None = None) -> list[NodeSample]:
        query = "SELECT * FROM node_samples"
        args: tuple = ()
        if node_id is not None:
            query += " WHERE node_id = ?"
            args = (node_id,)
        query += " ORDER BY node_id, timestamp"
        return [NodeSample(row[0], parse_time(row[1]), *row[2:])
                for row in self.db.execute(query, args)]

    def nodes(self) -> list[str]:
        return [row[0] for row in self.db.execute(
            "SELECT DISTINCT node_id FROM node_samples ORDER BY node_id")]

    def recent(self, node_id: str, limit: int) -> list[NodeSample]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        rows = self.db.execute(
            "SELECT * FROM node_samples WHERE node_id = ? "
            "ORDER BY timestamp DESC LIMIT ?", (node_id, limit)).fetchall()
        return [NodeSample(row[0], parse_time(row[1]), *row[2:])
                for row in reversed(rows)]

    def close(self) -> None:
        self.db.close()


def read_events(path: str | Path) -> Iterable[NodeSample]:
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield NodeSample.from_event(json.loads(line))
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"{path}:{line_number}: {exc}") from exc
