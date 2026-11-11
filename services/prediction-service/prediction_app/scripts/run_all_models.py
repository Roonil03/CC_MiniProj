"""Run, resume, visualize, and package a complete prediction model sweep.

The runner is intentionally offline: it trains against the supplied recorded
telemetry database and never starts an API, NATS consumer, Kubernetes client,
or live workload. Every state transition is written as a timestamped JSONL
event with host/process telemetry. Neural training emits one event per epoch
through the callback added to :mod:`prediction_app.models`.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover - documented as an optional fallback
    psutil = None

from ..data import METRICS, SampleStore
from ..training import KINDS, run_training

REPO_ROOT = Path(__file__).resolve().parents[4]
SERVICE_ROOT = REPO_ROOT / "services" / "prediction-service"
DEFAULT_RUN_DIR = REPO_ROOT / "experiments" / "runs" / "model-sweep"
STATE_FILE = "run_state.json"
EVENTS_FILE = "events.jsonl"
TIMELINE_FILE = "timeline.json"
SUMMARY_FILE = "summary.json"
ESTIMATE_FILE = "runtime_estimate.json"
ARCHIVE_SUFFIX = ".zip"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-c", f"safe.directory={REPO_ROOT}", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unavailable"


def system_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "timestamp": utc_now(),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "pid": os.getpid(),
    }
    if psutil is None:
        snapshot["psutil"] = "unavailable"
        return snapshot
    process = psutil.Process()
    memory = psutil.virtual_memory()
    cpu_times = process.cpu_times()
    snapshot.update({
        "psutil": psutil.__version__,
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": memory.percent,
        "memory_available_bytes": memory.available,
        "process_rss_bytes": process.memory_info().rss,
        "process_cpu_user_seconds": cpu_times.user,
        "process_cpu_system_seconds": cpu_times.system,
    })
    return snapshot


class EventRecorder:
    """Append-only event log plus an atomically updated JSON timeline."""

    def __init__(self, run_dir: Path, logger: logging.Logger) -> None:
        self.run_dir = run_dir
        self.logger = logger
        self.events_path = run_dir / EVENTS_FILE
        self.timeline_path = run_dir / TIMELINE_FILE
        self.started = time.perf_counter()
        self.events: list[dict[str, Any]] = []
        if self.events_path.exists():
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        self.events.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Ignoring malformed prior event line")

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {
            "timestamp": utc_now(),
            "run_elapsed_seconds": round(time.perf_counter() - self.started, 6),
            "event": event,
            "system": system_snapshot(),
            **fields,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
        self.events.append(record)
        write_json(self.timeline_path, self.events)
        detail = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
        self.logger.info("%s%s", event, f" {detail}" if detail else "")
        return record


def configure_logging(run_dir: Path) -> logging.Logger:
    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("dt_ram.model_sweep")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime
    file_handler = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def job_key(model: str, metric: str) -> str:
    return f"{model}__{metric}"


def make_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "models": list(args.models),
        "metrics": list(args.metrics),
        "history_steps": args.history_steps,
        "horizons": list(args.horizons),
        "period_seconds": args.period_seconds,
        "seed": args.seed,
        "epochs": args.epochs,
        "source_label": args.source_label,
        "db": str(Path(args.db).resolve()),
    }


def new_state(config: dict[str, Any]) -> dict[str, Any]:
    jobs = {}
    for metric in config["metrics"]:
        for model in config["models"]:
            jobs[job_key(model, metric)] = {
                "model": model,
                "metric": metric,
                "status": "pending",
                "attempts": 0,
                "started_at": None,
                "completed_at": None,
                "duration_seconds": None,
                "result_file": None,
                "error": None,
            }
    return {
        "version": 1,
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "git_commit": git_commit(),
        "config": config,
        "jobs": jobs,
        "status": "pending",
        "started_at": None,
        "completed_at": None,
    }


def load_or_create_state(run_dir: Path, config: dict[str, Any], fresh: bool, logger: logging.Logger) -> dict[str, Any]:
    path = run_dir / STATE_FILE
    if path.exists() and not fresh:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("config") != config:
            raise ValueError("existing run configuration differs; use a new --run-dir or --fresh")
        for job in state.get("jobs", {}).values():
            if job.get("status") == "running":
                job["status"] = "pending"
                job["error"] = "previous process stopped during this job"
        logger.info("Resuming run_id=%s", state.get("run_id"))
        return state
    if path.exists() and fresh:
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        backup_dir = run_dir / "previous" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_dir.mkdir(parents=True)
        for old in list(run_dir.iterdir()):
            if old.name != "previous":
                shutil.move(str(old), str(backup_dir / old.name))
        logger.info("Moved prior run outputs to %s", backup_dir)
    state = new_state(config)
    write_json(path, state)
    return state


def save_state(run_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    write_json(run_dir / STATE_FILE, state)


def estimate_job_seconds(model: str, epochs: int, completed: list[dict[str, Any]]) -> tuple[float, str]:
    matching = [
        float(job["duration_seconds"])
        for job in completed
        if job.get("model") == model and job.get("duration_seconds") is not None
    ]
    if matching:
        return sum(matching) / len(matching), "historical_same_model"
    heuristic = {
        "persistence": 1.0,
        "arima": 15.0,
        "ets": 8.0,
        "lstm": max(5.0, epochs * 0.12),
        "gru": max(5.0, epochs * 0.10),
        "temporal": max(4.0, epochs * 0.07),
        "transformer": max(5.0, epochs * 0.10),
    }
    return heuristic.get(model, 10.0), "host_independent_heuristic"


def write_estimate(run_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    completed = list(state.get("jobs", {}).values())
    rows = []
    for key, job in state.get("jobs", {}).items():
        if job.get("status") == "completed":
            estimate = float(job.get("duration_seconds") or 0.0)
            method = "observed"
        else:
            estimate, method = estimate_job_seconds(job["model"], state["config"]["epochs"], completed)
        rows.append({"job": key, "model": job["model"], "metric": job["metric"],
                     "status": job.get("status"), "estimated_seconds": round(estimate, 3),
                     "method": method})
    remaining = sum(row["estimated_seconds"] for row in rows if row["status"] != "completed")
    total = sum(row["estimated_seconds"] for row in rows)
    estimate = {
        "generated_at": utc_now(),
        "run_id": state["run_id"],
        "estimate_method": "observed durations when available, otherwise model heuristic",
        "jobs": rows,
        "estimated_total_seconds": round(total, 3),
        "estimated_remaining_seconds": round(remaining, 3),
        "estimated_total_human": format_duration(total),
        "estimated_remaining_human": format_duration(remaining),
    }
    write_json(run_dir / ESTIMATE_FILE, estimate)
    return estimate


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def run_job(args: argparse.Namespace, run_dir: Path, state: dict[str, Any], recorder: EventRecorder,
            logger: logging.Logger, key: str) -> None:
    job = state["jobs"][key]
    model, metric = job["model"], job["metric"]
    max_attempts = args.max_attempts
    result_path = run_dir / "results" / f"{key}.json"
    # Each invocation gets a bounded retry budget; attempts remains cumulative
    # so a failed run can be resumed without requiring --fresh.
    previous_attempts = int(job.get("attempts", 0))
    for attempt in range(previous_attempts + 1, previous_attempts + max_attempts + 1):
        job.update({"status": "running", "attempts": attempt, "started_at": utc_now(), "error": None})
        save_state(run_dir, state)
        recorder.emit("job_started", job=key, model=model, metric=metric, attempt=attempt)
        start = time.perf_counter()

        def progress(stats: dict[str, Any]) -> None:
            recorder.emit("epoch", job=key, model=model, metric=metric, attempt=attempt, **stats)

        try:
            result = run_training(
                args.db,
                str(run_dir / "models"),
                metric=metric,
                kind=model,
                history_steps=args.history_steps,
                horizons=tuple(args.horizons),
                period_seconds=args.period_seconds,
                seed=args.seed,
                epochs=args.epochs,
                source_label=args.source_label,
                progress=progress,
            )
            duration = time.perf_counter() - start
            write_json(result_path, result)
            job.update({"status": "completed", "completed_at": utc_now(),
                        "duration_seconds": round(duration, 6), "result_file": str(result_path), "error": None})
            save_state(run_dir, state)
            recorder.emit("job_completed", job=key, model=model, metric=metric, attempt=attempt,
                          duration_seconds=round(duration, 6), model_id=result.get("model_id"),
                          metrics=result.get("metrics"), inference_latency_ms=result.get("inference_latency_ms"))
            return
        except Exception as exc:  # continue/retry while retaining the full traceback in the log
            duration = time.perf_counter() - start
            message = f"{type(exc).__name__}: {exc}"
            job.update({"status": "failed", "duration_seconds": round(duration, 6), "error": message})
            save_state(run_dir, state)
            recorder.emit("job_failed", job=key, model=model, metric=metric, attempt=attempt,
                          duration_seconds=round(duration, 6), error=message)
            logger.error("Job %s failed on attempt %d (this invocation %d/%d)",
                         key, attempt, attempt - previous_attempts, max_attempts, exc_info=True)
            if attempt - previous_attempts < max_attempts:
                delay = args.retry_delay_seconds * (2 ** (attempt - previous_attempts - 1))
                recorder.emit("retry_scheduled", job=key, attempt=attempt, delay_seconds=delay)
                time.sleep(delay)
            elif args.fail_fast:
                raise


def read_results(run_dir: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for key, job in state.get("jobs", {}).items():
        if job.get("status") != "completed" or not job.get("result_file"):
            continue
        path = Path(job["result_file"])
        if not path.is_absolute():
            path = run_dir / path
        if path.exists():
            results.append(json.loads(path.read_text(encoding="utf-8")))
    return results


def plot_results(run_dir: Path, state: dict[str, Any], recorder: EventRecorder, logger: logging.Logger) -> None:
    plots = run_dir / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        write_json(plots / "graphs_unavailable.json", {"reason": str(exc), "generated_at": utc_now()})
        logger.warning("Graphs unavailable: install matplotlib to render plots")
        return

    results = read_results(run_dir, state)
    events = recorder.events
    completed_jobs = [job for job in state["jobs"].values() if job.get("status") == "completed"]

    # 1. Actual versus estimated job durations.
    if completed_jobs:
        labels = [f"{job['model']}\n{job['metric']}" for job in completed_jobs]
        actual = [float(job.get("duration_seconds") or 0) for job in completed_jobs]
        estimates = []
        for job in completed_jobs:
            estimate, _ = estimate_job_seconds(job["model"], state["config"]["epochs"], completed_jobs)
            estimates.append(estimate)
        fig, ax = plt.subplots(figsize=(max(10, len(labels) * 1.2), 6))
        positions = list(range(len(labels)))
        ax.bar([p - 0.2 for p in positions], actual, width=0.4, label="actual")
        ax.bar([p + 0.2 for p in positions], estimates, width=0.4, label="estimate")
        ax.set_xticks(positions, labels, rotation=45, ha="right")
        ax.set_ylabel("seconds")
        ax.set_title("Model runtime: actual versus estimate")
        ax.legend()
        fig.tight_layout()
        fig.savefig(plots / "runtime_actual_vs_estimate.png", dpi=150)
        plt.close(fig)

    # 2. Forecast metrics for every horizon and model, one figure per metric.
    for metric in state["config"]["metrics"]:
        metric_results = [result for result in results if result.get("metric") == metric]
        if not metric_results:
            continue
        metric_names = ("mae", "rmse", "mape", "r2", "interval_coverage")
        horizons = [str(horizon) for horizon in state["config"]["horizons"]]
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), squeeze=False)
        for axis, metric_name in zip(axes.flat, metric_names):
            for result in metric_results:
                values = [result.get("metrics", {}).get("test", {}).get(horizon, {}).get(metric_name) for horizon in horizons]
                values = [float(value) if value is not None else float("nan") for value in values]
                axis.plot(horizons, values, marker="o", label=result.get("kind", "unknown"))
            axis.set_title(metric_name)
            axis.set_xlabel("horizon seconds")
            axis.grid(alpha=0.3)
        axes.flat[-1].axis("off")
        handles, labels = axes.flat[0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="lower center", ncol=4)
        fig.suptitle(f"Forecast test metrics: {metric}")
        fig.tight_layout(rect=(0, 0.07, 1, 0.95))
        fig.savefig(plots / f"metrics_{metric}.png", dpi=150)
        plt.close(fig)

    # 3. Inference latency and artifact sizes.
    if results:
        labels = [f"{r.get('kind')}\n{r.get('metric')}" for r in results]
        latency = [float(r.get("inference_latency_ms", {}).get("test_mean", 0.0)) for r in results]
        artifact = [int((run_dir / "models" / r["weights_file"]).stat().st_size)
                    if r.get("weights_file") and (run_dir / "models" / r["weights_file"]).is_file()
                    else 0 for r in results]
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        axes[0].bar(labels, latency)
        axes[0].set_title("Mean test inference latency")
        axes[0].set_ylabel("milliseconds")
        axes[0].tick_params(axis="x", rotation=45)
        axes[1].bar(labels, artifact)
        axes[1].set_title("Model artifact size")
        axes[1].set_ylabel("bytes")
        axes[1].tick_params(axis="x", rotation=45)
        fig.tight_layout()
        fig.savefig(plots / "latency_and_artifact_size.png", dpi=150)
        plt.close(fig)

    # 4. System telemetry sampled at every event.
    telemetry = [(event.get("run_elapsed_seconds", 0), event.get("system", {})) for event in events]
    if telemetry:
        elapsed = [float(item[0]) for item in telemetry]
        cpu = [item[1].get("cpu_percent") for item in telemetry]
        memory = [item[1].get("memory_percent") for item in telemetry]
        rss = [item[1].get("process_rss_bytes", 0) / 1024 / 1024 for item in telemetry]
        fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
        axes[0].plot(elapsed, cpu, marker=".")
        axes[0].set_ylabel("host CPU %")
        axes[1].plot(elapsed, memory, marker=".")
        axes[1].set_ylabel("host memory %")
        axes[2].plot(elapsed, rss, marker=".")
        axes[2].set_ylabel("process RSS MiB")
        axes[2].set_xlabel("run elapsed seconds")
        fig.suptitle("System telemetry during run")
        fig.tight_layout()
        fig.savefig(plots / "system_telemetry.png", dpi=150)
        plt.close(fig)

    # 5. Neural epoch losses.
    epochs = [event for event in events if event.get("event") == "epoch"]
    if epochs:
        fig, ax = plt.subplots(figsize=(12, 6))
        jobs = sorted({event.get("job") for event in epochs})
        for key in jobs:
            rows = [event for event in epochs if event.get("job") == key]
            ax.plot([row["epoch"] for row in rows], [row["train_loss"] for row in rows], marker=".", label=f"{key} train")
            ax.plot([row["epoch"] for row in rows], [row["validation_loss"] for row in rows], linestyle="--", label=f"{key} validation")
        ax.set_xlabel("epoch")
        ax.set_ylabel("scaled MSE")
        ax.set_title("Training and validation loss by epoch")
        ax.legend(fontsize="small", ncol=2)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(plots / "epoch_losses.png", dpi=150)
        plt.close(fig)

    recorder.emit("plots_completed", plot_files=sorted(str(path.relative_to(run_dir)) for path in plots.glob("*")))


def package_run(run_dir: Path) -> Path:
    archive = run_dir.with_suffix(ARCHIVE_SUFFIX)
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(run_dir.rglob("*")):
            if "previous" in path.relative_to(run_dir).parts:
                continue
            if path.is_file() and path.suffix.lower() not in {".env", ".pem", ".key"}:
                bundle.write(path, path.relative_to(run_dir).as_posix())
    return archive


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(SERVICE_ROOT / "data" / "node_samples.sqlite"))
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    parser.add_argument("--models", nargs="+", choices=KINDS, default=list(KINDS))
    parser.add_argument("--metrics", nargs="+", choices=METRICS, default=["cpu"])
    parser.add_argument("--history-steps", type=int, default=60)
    parser.add_argument("--horizons", type=int, nargs="+", default=[5, 10, 30, 60])
    parser.add_argument("--period-seconds", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--source-label", default="recorded-telemetry")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=float, default=2.0)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="start a new state in the same run directory")
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--package-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir = Path(args.run_dir).expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = configure_logging(run_dir)

    if args.package_only:
        archive = package_run(run_dir)
        print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size}, indent=2))
        return 0

    config = make_config(args)
    state = load_or_create_state(run_dir, config, args.fresh, logger)
    if args.fresh:
        logger = configure_logging(run_dir)
    recorder = EventRecorder(run_dir, logger)
    recorder.emit("run_started", run_id=state["run_id"], config=config, system=system_snapshot())
    write_json(run_dir / "system.json", system_snapshot())
    estimate = write_estimate(run_dir, state)
    recorder.emit("runtime_estimate", estimated_total_seconds=estimate["estimated_total_seconds"],
                  estimated_remaining_seconds=estimate["estimated_remaining_seconds"],
                  estimated_total_human=estimate["estimated_total_human"])

    if args.estimate_only:
        recorder.emit("estimate_completed")
        archive = package_run(run_dir)
        print(json.dumps({"estimate": estimate, "archive": str(archive)}, indent=2))
        return 0
    if not Path(args.db).exists():
        recorder.emit("run_failed", error=f"database does not exist: {args.db}")
        logger.error("Database does not exist: %s", args.db)
        package_run(run_dir)
        return 2
    if args.max_attempts <= 0:
        raise ValueError("--max-attempts must be positive")

    state["status"] = "running"
    state["started_at"] = state.get("started_at") or utc_now()
    save_state(run_dir, state)
    for key in state["jobs"]:
        if state["jobs"][key].get("status") == "completed":
            recorder.emit("job_skipped", job=key, reason="already completed")
            continue
        run_job(args, run_dir, state, recorder, logger, key)
        write_estimate(run_dir, state)

    failed = [key for key, job in state["jobs"].items() if job.get("status") != "completed"]
    state["status"] = "failed" if failed else "completed"
    state["completed_at"] = utc_now()
    save_state(run_dir, state)
    recorder.emit("run_completed", status=state["status"], failed_jobs=failed)
    plot_results(run_dir, state, recorder, logger)
    summary = {
        "run_id": state["run_id"],
        "status": state["status"],
        "created_at": state["created_at"],
        "completed_at": state["completed_at"],
        "git_commit": state["git_commit"],
        "config": state["config"],
        "jobs": state["jobs"],
        "failed_jobs": failed,
        "event_count": len(recorder.events),
        "plot_files": sorted(str(path.relative_to(run_dir)) for path in (run_dir / "plots").glob("*")),
    }
    write_json(run_dir / SUMMARY_FILE, summary)
    archive = package_run(run_dir)
    logger.info("Packaged run archive: %s (%d bytes)", archive, archive.stat().st_size)
    print(json.dumps({"status": state["status"], "failed_jobs": failed,
                      "archive": str(archive), "summary": str(run_dir / SUMMARY_FILE)}, indent=2))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
