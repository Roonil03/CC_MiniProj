"""Verify a prediction-collector JSONL export against its sidecar manifest.

The collector currently hashes LF bytes before a Windows text write can
translate newlines to CRLF. --normalize-lf repairs only that exact mismatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def verify(path: str | Path, *, normalize_lf: bool = False,
           expected_nodes: int | None = None,
           min_duration_seconds: float = 0,
           max_missing_fraction: float | None = None) -> dict:
    trace = Path(path)
    manifest_path = trace.with_suffix(trace.suffix + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("event_type") != "NODE_METRIC_UPDATED":
        raise ValueError("unsupported manifest schema or event type")
    if not isinstance(manifest.get("source_label"), str) or not manifest["source_label"].strip():
        raise ValueError("manifest source_label is missing")
    period = manifest.get("period_seconds")
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("manifest period_seconds must be positive")
    raw = trace.read_bytes()
    expected_hash = manifest.get("sha256")
    actual_hash = hashlib.sha256(raw).hexdigest()
    normalized = False
    if actual_hash != expected_hash:
        lf = raw.replace(b"\r\n", b"\n")
        if not normalize_lf or lf == raw or hashlib.sha256(lf).hexdigest() != expected_hash:
            raise ValueError("JSONL bytes do not match manifest SHA-256")
        trace.write_bytes(lf)
        raw = lf
        actual_hash = expected_hash
        normalized = True

    buckets: dict[str, set[int]] = defaultdict(set)
    last_by_node: dict[str, datetime] = {}
    first = last = None
    count = 0
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line:
            raise ValueError(f"blank JSONL line {line_number}")
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL line {line_number}") from exc
        if not isinstance(event, dict) or event.get("event_type") != "NODE_METRIC_UPDATED":
            raise ValueError(f"invalid event type on line {line_number}")
        node = event.get("node_id")
        if not isinstance(node, str) or not node.strip():
            raise ValueError(f"missing node_id on line {line_number}")
        timestamp = _time(event.get("timestamp"))
        if node in last_by_node and timestamp <= last_by_node[node]:
            raise ValueError(f"node {node} timestamps are not strictly increasing")
        last_by_node[node] = timestamp
        metrics = event.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError(f"missing metrics on line {line_number}")
        for name in ("cpu", "memory", "network_in", "network_out"):
            value = metrics.get(name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid {name} on line {line_number}")
            if name in ("cpu", "memory") and value > 1:
                raise ValueError(f"invalid {name} fraction on line {line_number}")
        buckets[node].add(math.floor(timestamp.timestamp() / period))
        first = timestamp if first is None else min(first, timestamp)
        last = timestamp if last is None else max(last, timestamp)
        count += 1
    if not count:
        raise ValueError("trace has no events")
    nodes = sorted(buckets)
    if expected_nodes is not None and len(nodes) != expected_nodes:
        raise ValueError(f"expected {expected_nodes} nodes, observed {len(nodes)}")
    quality = {node: {"observed_buckets": len(points),
                      "missing_buckets_within_span": max(points) - min(points) + 1 - len(points)}
               for node, points in buckets.items()}
    if max_missing_fraction is not None:
        if not 0 <= max_missing_fraction <= 1:
            raise ValueError("max_missing_fraction must be between 0 and 1")
        for node, result in quality.items():
            total = result["observed_buckets"] + result["missing_buckets_within_span"]
            if result["missing_buckets_within_span"] / total > max_missing_fraction:
                raise ValueError(f"node {node} missing-bucket fraction exceeds {max_missing_fraction:.3f}")
    duration = (last - first).total_seconds()
    if duration < min_duration_seconds:
        raise ValueError(f"trace duration {duration:.1f}s is below {min_duration_seconds:.1f}s")
    if (manifest.get("sample_count") != count or manifest.get("node_ids") != nodes or
            manifest.get("quality") != quality or
            _time(manifest.get("first_timestamp")) != first or
            _time(manifest.get("last_timestamp")) != last):
        raise ValueError("manifest counts, nodes, time span, or bucket quality differ from JSONL")
    return {"status": "verified", "source_label": manifest["source_label"],
            "sample_count": count, "node_ids": nodes, "duration_seconds": duration,
            "sha256": actual_hash, "normalized_lf": normalized, "quality": quality}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", help="collector JSONL path; sidecar manifest is required")
    parser.add_argument("--normalize-lf", action="store_true",
                        help="replace CRLF only when the resulting bytes match the manifest")
    parser.add_argument("--expected-nodes", type=int)
    parser.add_argument("--min-duration-seconds", type=float, default=0)
    parser.add_argument("--max-missing-fraction", type=float,
                        help="reject any node with more than this fraction of missing one-period buckets")
    args = parser.parse_args()
    if args.expected_nodes is not None and args.expected_nodes <= 0:
        parser.error("expected-nodes must be positive")
    if args.min_duration_seconds < 0:
        parser.error("min-duration-seconds cannot be negative")
    if args.max_missing_fraction is not None and not 0 <= args.max_missing_fraction <= 1:
        parser.error("max-missing-fraction must be between 0 and 1")
    print(json.dumps(verify(args.jsonl, normalize_lf=args.normalize_lf,
                            expected_nodes=args.expected_nodes,
                            min_duration_seconds=args.min_duration_seconds,
                            max_missing_fraction=args.max_missing_fraction), indent=2))


if __name__ == "__main__":
    main()
