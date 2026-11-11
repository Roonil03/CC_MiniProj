"""Prepare an offline SQLite prediction input from synthetic or local JSONL telemetry."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "prediction-service"))
from prediction_app.data import NodeSample, SampleStore, read_events  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=1800)
    parser.add_argument("--scenario", choices=("stable", "burst", "memory-pressure"), default="stable")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("output database already exists; use a fresh run directory")
    if args.input and (not args.input.is_file() or args.input.resolve() == args.output.resolve()):
        raise SystemExit("local input must be an existing, separate JSONL file")
    if args.count < 600:
        raise SystemExit("synthetic count must be at least 600")

    source = "local-export" if args.input else "synthetic"
    digest = hashlib.sha256(args.input.read_bytes()).hexdigest() if args.input else None
    rng = random.Random(args.seed)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    store = SampleStore(args.output)
    inserted = 0
    try:
        if args.input:
            rows = read_events(args.input)
        else:
            def synthetic():
                for index in range(args.count):
                    phase = 2 * math.pi * index / 240
                    burst = 0.35 if args.scenario == "burst" and index % 360 < 40 else 0.0
                    pressure = 0.35 if args.scenario == "memory-pressure" and index % 420 < 100 else 0.0
                    cpu = min(0.95, max(0.04, 0.40 + 0.10 * math.sin(phase) + burst + rng.uniform(-0.02, 0.02)))
                    memory = min(0.95, max(0.04, 0.50 + 0.06 * math.sin(phase / 2) + pressure + rng.uniform(-0.01, 0.01)))
                    yield NodeSample("synthetic-edge-a", start + timedelta(seconds=index), cpu, memory,
                                     100 + 15 * math.sin(phase) + rng.random() * 2,
                                     85 + 10 * math.sin(phase) + rng.random() * 2)
            rows = synthetic()
        for sample in rows:
            inserted += int(store.add(sample))
    finally:
        store.close()
    if inserted < 600:
        args.output.unlink(missing_ok=True)
        raise SystemExit("input contains fewer than 600 unique samples")
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "source": source,
                "synthetic": not bool(args.input), "seed": args.seed if not args.input else None,
                "sample_count": inserted, "scenario": args.scenario if not args.input else "user-provided",
                "input_path": str(args.input.resolve()) if args.input else None,
                "input_sha256": digest, "database_path": str(args.output.resolve()),
                "database_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}
    path = args.output.with_suffix(".manifest.json")
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
