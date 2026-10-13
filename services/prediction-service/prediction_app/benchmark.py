"""Measure selected model and HTTP latency on recorded data and this host."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from datetime import timezone
from pathlib import Path

import psutil
from fastapi.testclient import TestClient

from .data import SampleStore
from .features import bucketed
from .models import persistence, predict_neural
from .registry import Registry
from .service import create_app


def _percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    low = int(position)
    fraction = position - low
    return ordered[low] * (1 - fraction) + ordered[min(low + 1, len(ordered) - 1)] * fraction


def benchmark(db: str, registry_path: str, *, metric: str = "cpu",
              repeats: int = 50) -> dict:
    if repeats <= 0:
        raise ValueError("repeats must be positive")
    registry = Registry(registry_path)
    record = registry.selected(metric)
    if record is None:
        raise ValueError("activate a trained model before benchmarking")
    config = record["hyperparameters"]
    store = SampleStore(db)
    try:
        nodes = store.nodes()
        if not nodes:
            raise ValueError("no recorded telemetry")
        node_id = nodes[0]
        samples = store.recent(node_id, max(config["history_steps"] + 5, 180))
    finally:
        store.close()
    period = config["period_seconds"]
    rows = bucketed(samples, period)[node_id]
    origin_bucket = max(rows)
    keys = range(origin_bucket - config["history_steps"] + 1, origin_bucket + 1)
    if not all(key in rows for key in keys):
        raise ValueError("insufficient contiguous history")
    history = tuple(getattr(rows[key], metric) for key in keys)
    if record["kind"] == "persistence":
        forecast = lambda: persistence(history, tuple(config["horizons_seconds"]))
    else:
        network, scale = registry.load_network(record)
        forecast = lambda: predict_neural(network, scale, history)
    forecast()  # warm import, model load, and kernel initialization
    process = psutil.Process()
    rss_before = process.memory_info().rss
    cpu_before = process.cpu_times()
    durations = []
    for _ in range(repeats):
        started = time.perf_counter()
        forecast()
        durations.append(1000 * (time.perf_counter() - started))
    cpu_after = process.cpu_times()
    rss_after = process.memory_info().rss

    # Use the historical sample time as the API clock. This benchmark does
    # not simulate live freshness, which is covered by service tests.
    api = create_app(db_path=db, registry_path=registry_path,
                     now=lambda: samples[-1].timestamp.astimezone(timezone.utc))
    client = TestClient(api)
    import os
    token = os.getenv("DT_RAM_SERVICE_TOKEN")
    headers = {"x-service-token": token} if token else {}
    url = f"/predictions?node_id={node_id}&metric={metric}"
    if client.get(url, headers=headers).status_code != 200:
        raise ValueError("prediction API did not become ready")
    http_durations = []
    for _ in range(repeats):
        started = time.perf_counter()
        response = client.get(url, headers=headers)
        if response.status_code != 200:
            raise ValueError(f"prediction API returned {response.status_code}")
        http_durations.append(1000 * (time.perf_counter() - started))

    def summary(values):
        return {"mean_ms": statistics.mean(values), "median_ms": statistics.median(values),
                "p95_ms": _percentile(values, 0.95), "max_ms": max(values)}
    artifact = record.get("weights_file")
    return {
        "model_id": record["model_id"], "metric": metric,
        "dataset_version": record["training_dataset"], "repeats": repeats,
        "python": platform.python_version(), "platform": platform.platform(),
        "logical_cpus": psutil.cpu_count(),
        "direct_inference": summary(durations), "http_request": summary(http_durations),
        "process_cpu_seconds": (cpu_after.user + cpu_after.system
                                - cpu_before.user - cpu_before.system),
        "rss_before_bytes": rss_before, "rss_after_bytes": rss_after,
        "artifact_bytes": (Path(registry_path).parent / artifact).stat().st_size
        if artifact else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark an active prediction model")
    parser.add_argument("--db", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--metric", default="cpu")
    parser.add_argument("--repeats", type=int, default=50)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = benchmark(args.db, args.registry, metric=args.metric, repeats=args.repeats)
    payload = json.dumps(result, indent=2)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
