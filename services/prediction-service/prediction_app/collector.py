"""Replay Go telemetry JSONL or record its existing JetStream subject."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
from collections import defaultdict
from pathlib import Path

from .data import NodeSample, SampleStore, read_events

SUBJECT = "dt.telemetry.node_metric"
STREAM = "DT_TELEMETRY"


def export_events(store: SampleStore, output: str, *, source_label: str,
                  period_seconds: int = 1) -> dict:
    if not source_label.strip() or period_seconds <= 0:
        raise ValueError("source label and positive sampling period required")
    samples = store.samples()
    if not samples:
        raise ValueError("nothing to export")
    lines = [json.dumps(sample.to_event(), sort_keys=True) for sample in samples]
    payload = "\n".join(lines) + "\n"
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload, encoding="utf-8")
    buckets: dict[str, set[int]] = defaultdict(set)
    for sample in samples:
        buckets[sample.node_id].add(math.floor(sample.timestamp.timestamp() / period_seconds))
    quality = {node: {"observed_buckets": len(points),
                      "missing_buckets_within_span": max(points) - min(points) + 1 - len(points)}
               for node, points in buckets.items()}
    manifest = {"schema_version": 1, "event_type": "NODE_METRIC_UPDATED",
                "source_label": source_label, "sample_count": len(samples),
                "node_ids": sorted(buckets), "period_seconds": period_seconds,
                "first_timestamp": min(s.timestamp for s in samples).isoformat(),
                "last_timestamp": max(s.timestamp for s in samples).isoformat(),
                "sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "quality": quality}
    target.with_suffix(target.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


async def record_message(store: SampleStore, message) -> bool:
    try:
        sample = NodeSample.from_event(json.loads(message.data))
    except (ValueError, TypeError) as exc:
        logging.warning("invalid telemetry event: %s", exc)
        await message.term()
        return False
    inserted = store.add(sample)  # SQLite commit precedes acknowledgement.
    await message.ack()
    return inserted


async def record_nats(store: SampleStore, url: str) -> None:
    import nats
    from nats.errors import TimeoutError as NatsTimeout

    connection = await nats.connect(url)
    try:
        jetstream = connection.jetstream()
        subscriber = await jetstream.pull_subscribe(
            SUBJECT, durable="prediction-recorder", stream=STREAM)
        while True:
            try:
                messages = await subscriber.fetch(10, timeout=2)
            except NatsTimeout:
                continue
            for message in messages:
                await record_message(store, message)
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Record DT-RAM node telemetry")
    parser.add_argument("--db", required=True, help="local SQLite recording path")
    actions = parser.add_subparsers(dest="command", required=True)
    replay = actions.add_parser("import", help="import NODE_METRIC_UPDATED JSONL")
    replay.add_argument("jsonl")
    listen = actions.add_parser("listen", help="consume the implemented JetStream subject")
    listen.add_argument("--nats-url", default="nats://localhost:4222")
    export = actions.add_parser("export", help="write replayable JSONL plus data-quality manifest")
    export.add_argument("--output", required=True)
    export.add_argument("--source-label", required=True)
    export.add_argument("--period-seconds", type=int, default=1)
    args = parser.parse_args()
    store = SampleStore(args.db)
    try:
        if args.command == "import":
            added = sum(store.add(sample) for sample in read_events(args.jsonl))
            print(json.dumps({"added": added, "total": len(store.samples())}))
        elif args.command == "export":
            print(json.dumps(export_events(store, args.output,
                                           source_label=args.source_label,
                                           period_seconds=args.period_seconds)))
        else:
            asyncio.run(record_nats(store, args.nats_url))
    finally:
        store.close()


if __name__ == "__main__":
    main()
