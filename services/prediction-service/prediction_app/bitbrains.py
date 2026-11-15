"""Import bounded Bitbrains fastStorage VM observations into a new offline store."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from .data import NodeSample, SampleStore

SOURCE = "https://atlarge-research.com/gwa-t-12/"
DOWNLOAD = "https://atlarge-research.com/gwa-traces/gwa_t_12_fastStorage.zip"


def import_trace(archive: str, db: str, max_vms: int = 5) -> dict:
    if max_vms < 1:
        raise ValueError("max_vms must be positive")
    path, target = Path(archive), Path(db)
    manifest_path = Path(str(target) + ".manifest.json")
    if target.exists() or manifest_path.exists():
        raise ValueError("destination database or manifest already exists")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    rows_imported = rows_skipped = duplicates = 0
    counts = {"seconds": 0, "milliseconds": 0}
    gaps = {}
    selected = []
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path) as archive_file:
        names = sorted(n for n in archive_file.namelist() if n.lower().endswith(".csv"))[:max_vms]
        if not names:
            raise ValueError("archive has no CSV files")
        store = SampleStore(target)
        try:
            for name in names:
                vm = "bitbrains-" + Path(name).stem
                if vm in selected:
                    raise ValueError("duplicate VM filename")
                selected.append(vm)
                buckets = set()
                with archive_file.open(name) as raw:
                    reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig"), delimiter=";")
                    header = next(reader, None)
                    expected = ("timestamp", "cpu cores", "cpu capacity", "cpu usage",
                                "cpu usage", "memory capacity", "memory usage", "disk read",
                                "disk write", "network received", "network transmitted")
                    if (not header or len(header) != 11 or
                            any(not field.strip().lower().startswith(prefix)
                                for field, prefix in zip(header, expected))):
                        raise ValueError(f"unexpected CSV schema in {name}")
                    for row in reader:
                        try:
                            if len(row) != 11:
                                raise ValueError("wrong column count")
                            values = [float(x.strip()) for x in row]
                            if not all(math.isfinite(x) for x in values):
                                raise ValueError("non-finite value")
                            stamp = values[0]
                            # The source describes milliseconds but published raw examples
                            # use seconds. Accept either representation only in trace era.
                            unit = "milliseconds" if stamp >= 1e12 else "seconds"
                            seconds = stamp / 1000 if unit == "milliseconds" else stamp
                            if not 1_360_000_000 <= seconds < 1_400_000_000:
                                raise ValueError("timestamp outside trace era")
                            cpu, capacity, used = values[4] / 100, values[5], values[6]
                            net_in, net_out = values[9] * .008, values[10] * .008
                            if capacity <= 0 or not 0 <= cpu <= 1 or not 0 <= used <= capacity or min(net_in, net_out) < 0:
                                raise ValueError("invalid resource observation")
                            sample = NodeSample(vm, datetime.fromtimestamp(seconds, timezone.utc),
                                                cpu, used / capacity, net_in, net_out)
                            if store.add(sample):
                                rows_imported += 1
                                counts[unit] += 1
                                buckets.add(int(seconds // 300))
                            else:
                                duplicates += 1
                        except (ValueError, OverflowError, OSError):
                            rows_skipped += 1
                gaps[vm] = (max(buckets) - min(buckets) + 1 - len(buckets)) if buckets else None
        finally:
            store.close()
    if not rows_imported:
        raise ValueError("no valid observations imported")
    manifest = {"dataset": "GWA-T-12 Bitbrains fastStorage", "source_url": SOURCE,
                "download_url": DOWNLOAD, "archive_sha256": digest.hexdigest(),
                "selected_vms": selected, "rows_imported": rows_imported,
                "rows_skipped": rows_skipped, "duplicate_rows": duplicates, "cadence_seconds": 300,
                "missing_buckets_by_vm": gaps, "timestamp_representation_counts": counts,
                "units": {"cpu": "fraction of provisioned CPU", "memory": "active KB / provisioned KB",
                          "network_in": "Mbps", "network_out": "Mbps"},
                "conversion": "CPU percent / 100; network KB/s * 0.008; rows with invalid or missing values omitted",
                "scope": "VM observations, not physical host telemetry"}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, help="downloaded official fastStorage ZIP")
    parser.add_argument("--db", required=True, help="new output SQLite database")
    parser.add_argument("--max-vms", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(import_trace(args.archive, args.db, args.max_vms), indent=2))


if __name__ == "__main__":
    main()

