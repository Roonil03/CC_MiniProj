"""Offline reproducible model comparison and versioned artifact creation."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .data import METRICS, SampleStore
from .evaluation import metrics, observed_coverage, residual_radius
from .features import build_windows, split_windows
from .models import fit_neural, persistence, predict_neural, statistical

KINDS = ("persistence", "arima", "ets", "lstm", "gru", "temporal", "transformer")


def _versions() -> dict[str, str]:
    result = {"python": platform.python_version()}
    for name in ("torch", "statsmodels"):
        try:
            module = __import__(name)
            result[name] = module.__version__
        except ImportError:
            result[name] = "unavailable"
    return result


def _git_info() -> dict[str, str | bool]:
    root = Path(__file__).resolve().parents[3]
    cmd = ["git", "-c", f"safe.directory={root}"]
    try:
        commit = subprocess.check_output(cmd + ["rev-parse", "HEAD"], cwd=root,
                                         stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(cmd + ["status", "--porcelain"], cwd=root,
                                             stderr=subprocess.DEVNULL, text=True).strip())
        return {"git_commit": commit, "working_tree_dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": "unavailable", "working_tree_dirty": True}


def _dataset_hash(samples) -> str:
    payload = "\n".join(json.dumps(sample.to_dict(), sort_keys=True)
                        for sample in samples).encode()
    return hashlib.sha256(payload).hexdigest()


def _source_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).resolve().parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _evaluate(windows, forecast, horizons) -> tuple[dict, list[list[float]], float]:
    predicted = []
    started = time.perf_counter()
    for window in windows:
        predicted.append(forecast(window.history))
    elapsed_ms = 1000 * (time.perf_counter() - started) / max(1, len(windows))
    report = {str(h): metrics([w.targets[i] for w in windows],
                              [p[i] for p in predicted])
              for i, h in enumerate(horizons)}
    return report, predicted, elapsed_ms


def _subsample(windows, limit=64):
    if len(windows) <= limit:
        return windows
    return [windows[int(i * (len(windows) - 1) / (limit - 1))] for i in range(limit)]


def _validation_regions(windows, max_horizon: int):
    origins = sorted({window.origin for window in windows})
    if len(origins) < 4:
        raise ValueError("validation period too short")
    calibration_start = origins[len(origins) // 2]
    audit_start = origins[3 * len(origins) // 4]
    gap = timedelta(seconds=max_horizon)
    tune = [w for w in windows if w.origin + gap < calibration_start]
    calibrate = [w for w in windows if calibration_start <= w.origin
                 and w.origin + gap < audit_start]
    audit = [w for w in windows if w.origin >= audit_start]
    if not tune or not calibrate or not audit:
        raise ValueError("validation period too short after horizon guard gaps")
    return tune, calibrate, audit


def _spaced(windows, minimum_seconds: int):
    """Use distinct forecast periods when measuring interval coverage."""
    selected = []
    last_origin = None
    gap = timedelta(seconds=minimum_seconds)
    for window in windows:
        if last_origin is None or window.origin - last_origin >= gap:
            selected.append(window)
            last_origin = window.origin
    return selected


def run_training(db: str, output: str, *, metric: str = "cpu", kind: str = "persistence",
                 history_steps: int = 60, horizons: tuple[int, ...] = (5, 10, 30, 60),
                 period_seconds: int = 1, seed: int = 42, epochs: int = 20,
                 source_label: str, progress: Callable[[dict], None] | None = None) -> dict:
    if metric not in METRICS or kind not in KINDS:
        raise ValueError("unsupported metric or model")
    if not source_label.strip():
        raise ValueError("source_label is required for dataset provenance")
    store = SampleStore(db)
    try:
        samples = store.samples()
    finally:
        store.close()
    windows = build_windows(samples, metric, history_steps=history_steps,
                            horizons_seconds=horizons, period_seconds=period_seconds)
    parts = split_windows(windows, horizons_seconds=horizons)
    if not all(parts.values()):
        raise ValueError("insufficient contiguous history in one or more chronological partitions")
    # Model selection, interval calibration, and coverage assessment are
    # separate contiguous regions within the validation period.
    validation = parts["validation"]
    tune, calibrate, audit = _validation_regions(validation, max(horizons))
    calibrate = _spaced(calibrate, max(horizons))
    audit = _spaced(audit, max(horizons))
    if kind in ("arima", "ets") and history_steps < 12:
        raise ValueError("statistical models need at least 12 history steps")
    if kind in ("arima", "ets"):
        # Per-origin statistical refits are expensive; cap calibration and
        # audit work. Tuning/test scores use common sampled origins below.
        calibrate, audit = map(_subsample, (calibrate, audit))

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)
    network = scale = None
    fit_info = {}
    if kind == "persistence":
        forecast = lambda history: persistence(history, horizons)
    elif kind in ("arima", "ets"):
        forecast = lambda history: statistical(kind, history, horizons, period_seconds)
    else:
        network, scale, fit_info = fit_neural(
            kind, parts["train"], tune, history_steps=history_steps,
            horizons=horizons, seed=seed, epochs=epochs, progress=progress)
        forecast = lambda history: predict_neural(network, scale, history)

    tune_report, _, latency_ms = _evaluate(_subsample(tune), forecast, horizons)
    _, cal_preds, _ = _evaluate(calibrate, forecast, horizons)
    _, audit_preds, _ = _evaluate(audit, forecast, horizons)
    radii = {}
    confidence = {}
    for i, horizon in enumerate(horizons):
        cal_actual = [w.targets[i] for w in calibrate]
        cal_predicted = [p[i] for p in cal_preds]
        radius = residual_radius(cal_actual, cal_predicted)
        radii[str(horizon)] = radius
        audit_actual = [w.targets[i] for w in audit]
        audit_predicted = [p[i] for p in audit_preds]
        coverage = observed_coverage(audit_actual, audit_predicted, radius["radius"])
        # Wilson 95% lower bound. It represents observed past interval
        # reliability, not a per-forecast probability of correctness.
        n = len(audit)
        z = 1.96
        lower = (coverage + z*z/(2*n) - z*((coverage*(1-coverage)/n
                 + z*z/(4*n*n))**0.5)) / (1 + z*z/n)
        confidence[str(horizon)] = {"audit_coverage": coverage,
                                    "audit_count": n,
                                    "coverage_lower_bound": lower if n >= 30 else None}
    test = _subsample(parts["test"])
    test_report, test_predictions, test_latency_ms = _evaluate(test, forecast, horizons)
    for i, horizon in enumerate(horizons):
        test_report[str(horizon)]["interval_coverage"] = observed_coverage(
            [w.targets[i] for w in test], [p[i] for p in test_predictions],
            radii[str(horizon)]["radius"])

    dataset_version = _dataset_hash(samples)
    source_hash = _source_hash()
    git_info = _git_info()
    software = _versions()
    trained_at = datetime.now(timezone.utc).isoformat()
    config = {"metric": metric, "kind": kind, "history_steps": history_steps,
              "horizons_seconds": list(horizons), "period_seconds": period_seconds,
              "seed": seed, "epochs": epochs}
    version = hashlib.sha256(json.dumps({"dataset": dataset_version, "config": config,
                                        "source": source_hash, "git": git_info,
                                        "software": software, "trained_at": trained_at},
                                       sort_keys=True).encode()).hexdigest()[:16]
    model_id = f"{kind}-{metric}-{version}"
    weights_file = None
    artifact_hash = None
    if network is not None:
        import torch
        weights_file = f"{model_id}.pt"
        torch.save(network.state_dict(), output_path / weights_file)
        artifact_hash = hashlib.sha256((output_path / weights_file).read_bytes()).hexdigest()
    record = {
        "model_id": model_id, "version": version, "kind": kind, "metric": metric,
        "training_dataset": dataset_version,
        "dataset_source": source_label,
        "dataset_samples": len(samples),
        "dataset_nodes": sorted({sample.node_id for sample in samples}),
        "dataset_period": {"first": min(s.timestamp for s in samples).isoformat(),
                           "last": max(s.timestamp for s in samples).isoformat()},
        "training_timestamp": trained_at,
        "hyperparameters": config, "fit": fit_info, "software": software,
        "source_sha256": source_hash,
        "training_windows": len(parts["train"]),
        "validation_windows": len(validation), "test_windows": len(test),
        "metrics": {"validation": tune_report, "test": test_report},
        "inference_latency_ms": {"validation_mean": latency_ms,
                                  "test_mean": test_latency_ms},
        "calibration": radii, "confidence": confidence,
        "weights_file": weights_file, "artifact_hash": artifact_hash,
        "scale": {"center": scale.center, "spread": scale.spread} if scale else None,
        **git_info,
    }
    registry = output_path / "registry.json"
    records = json.loads(registry.read_text(encoding="utf-8")) if registry.exists() else []
    records = [r for r in records if r["model_id"] != model_id] + [record]
    registry.write_text(json.dumps(records, indent=2, allow_nan=False), encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate one DT-RAM forecast model")
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metric", choices=METRICS, default="cpu")
    parser.add_argument("--model", choices=KINDS, required=True)
    parser.add_argument("--history-steps", type=int, default=60)
    parser.add_argument("--period-seconds", type=int, default=1)
    parser.add_argument("--horizons", type=int, nargs="+", default=[5, 10, 30, 60])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--source-label", required=True,
                        help="document the real collection or named test fixture")
    args = parser.parse_args()
    record = run_training(args.db, args.output, metric=args.metric, kind=args.model,
                          history_steps=args.history_steps,
                          period_seconds=args.period_seconds,
                          horizons=tuple(args.horizons), seed=args.seed,
                          epochs=args.epochs, source_label=args.source_label)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
