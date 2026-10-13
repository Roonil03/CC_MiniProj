"""Causal, regularly spaced forecasting windows and chronological splits."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from .data import METRICS, NodeSample


@dataclass(frozen=True)
class Window:
    node_id: str
    metric: str
    origin: datetime
    history: tuple[float, ...]
    targets: tuple[float, ...]


def bucketed(samples: list[NodeSample], period_seconds: int) -> dict[str, dict[int, NodeSample]]:
    if period_seconds <= 0:
        raise ValueError("period_seconds must be positive")
    by_node: dict[str, dict[int, NodeSample]] = defaultdict(dict)
    for sample in sorted(samples, key=lambda s: s.timestamp):
        bucket = math.floor(sample.timestamp.timestamp() / period_seconds)
        by_node[sample.node_id][bucket] = sample  # latest within each interval
    return dict(by_node)


def build_windows(samples: list[NodeSample], metric: str, *, history_steps: int = 60,
                  horizons_seconds: tuple[int, ...] = (5, 10, 30, 60),
                  period_seconds: int = 1) -> list[Window]:
    if metric not in METRICS or history_steps <= 0 or period_seconds <= 0 or not horizons_seconds:
        raise ValueError("invalid metric, history, or horizons")
    if any(h <= 0 or h % period_seconds for h in horizons_seconds):
        raise ValueError("horizons must be positive multiples of period_seconds")
    offsets = tuple(h // period_seconds for h in horizons_seconds)
    out = []
    for node_id, rows in bucketed(samples, period_seconds).items():
        for origin in sorted(rows):
            past = [origin - k for k in range(history_steps - 1, -1, -1)]
            future = [origin + k for k in offsets]
            if not all(k in rows for k in past + future):
                continue
            out.append(Window(node_id, metric,
                              datetime.fromtimestamp(origin * period_seconds, timezone.utc),
                              tuple(getattr(rows[k], metric) for k in past),
                              tuple(getattr(rows[k], metric) for k in future)))
    return sorted(out, key=lambda w: (w.origin, w.node_id))


def split_windows(windows: list[Window], *, horizons_seconds: tuple[int, ...],
                  fractions: tuple[float, float] = (0.6, 0.8)) -> dict[str, list[Window]]:
    """Assign by global clock; keep every label inside its origin partition."""
    if not 0 < fractions[0] < fractions[1] < 1 or not windows:
        raise ValueError("invalid split boundaries or empty windows")
    origins = sorted({w.origin for w in windows})
    first = origins[int(len(origins) * fractions[0])]
    second = origins[int(len(origins) * fractions[1])]
    result: dict[str, list[Window]] = {"train": [], "validation": [], "test": []}
    from datetime import timedelta
    max_horizon = timedelta(seconds=max(horizons_seconds))
    for window in windows:
        end = window.origin + max_horizon
        if window.origin < first and end < first:
            result["train"].append(window)
        elif first <= window.origin < second and end < second:
            result["validation"].append(window)
        elif second <= window.origin:
            result["test"].append(window)
    return result
