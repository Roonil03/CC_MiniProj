#!/usr/bin/env python3
"""Read-only Kubernetes or synthetic shadow-only DT-RAM simulation walkthrough.

The demo launchers pass ``--live`` so this prints an explicit list of what is
running locally as part of the demo simulation, then repaints a continuous
feed: each tick reads the local Kubernetes snapshot, updates the Digital
Twin, forecasts node utilization with the prediction-service models, and
re-evaluates counterfactual candidates through the safety gate. Nothing is
written to Kubernetes. ``--once`` prints a single snapshot instead.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time
import warnings


SIMULATION_SERVICE_ROOT = Path(__file__).resolve().parents[1] / "services" / "simulation-service"
PREDICTION_SERVICE_ROOT = Path(__file__).resolve().parents[1] / "services" / "prediction-service"
sys.path.insert(0, str(SIMULATION_SERVICE_ROOT))
sys.path.insert(0, str(PREDICTION_SERVICE_ROOT))

from app.safety import SafetyGate  # noqa: E402
from app.simulator import evaluate_candidates  # noqa: E402
from app.twin import TwinState  # noqa: E402
from prediction_app.models import persistence as persistence_model  # noqa: E402
from prediction_app.models import statistical as statistical_model  # noqa: E402


FEED_METRICS = ("cpu", "memory")
MAX_CONSECUTIVE_TICK_FAILURES = 10
_MIN_FORECAST_HISTORY = 12  # prediction_app statistical models need >= 12 samples

_STATS_AVAILABLE: bool | None = None


def available_forecast_models() -> list[str]:
    """Forecast model kinds the feed can run; statistical fits need statsmodels."""
    global _STATS_AVAILABLE
    if _STATS_AVAILABLE is None:
        try:
            import statsmodels  # noqa: F401

            _STATS_AVAILABLE = True
        except ImportError:
            _STATS_AVAILABLE = False
    if _STATS_AVAILABLE:
        return ["persistence", "arima", "ets"]
    return ["persistence"]


def build_demo(seed: int) -> tuple[TwinState, list[dict], list[dict]]:
    rng = random.Random(seed)
    twin = TwinState(stale_after_seconds=30)
    values = {
        "edge-hot": (0.88, 0.62),
        "edge-cool": (0.24, 0.38),
        "edge-stale": (0.42, 0.47),
    }
    now = datetime.now(timezone.utc)
    for node_id, (cpu, memory) in values.items():
        # Small deterministic variation makes --seed useful while keeping the
        # fixture's hot/cool/stale roles clear.
        cpu = round(cpu + rng.uniform(-0.015, 0.015), 3)
        memory = round(memory + rng.uniform(-0.015, 0.015), 3)
        timestamp = now - timedelta(minutes=3) if node_id == "edge-stale" else now
        twin.apply_telemetry(
            node_id,
            cpu,
            memory,
            network_in_mbps=18.0,
            network_out_mbps=12.0,
            timestamp=timestamp,
        )
    # Independent synthetic comparison samples: intentionally close to, but
    # not copied from, the twin telemetry so the fidelity score is meaningful.
    physical_samples = {
        "edge-hot": {"cpu": 0.90, "memory": 0.60, "network_in": 20.0, "network_out": 11.0},
        "edge-cool": {"cpu": 0.26, "memory": 0.40, "network_in": 16.0, "network_out": 13.0},
        "edge-stale": {"cpu": 0.40, "memory": 0.49, "network_in": 19.0, "network_out": 10.0},
    }
    twin.score_all(physical_samples)
    actions = [
        {"type": "NOOP", "source": "edge-hot", "label": "Keep current placement"},
        {"type": "SCALE", "source": "edge-hot", "replicas": 3, "label": "Scale hot service to 3"},
        {
            "type": "MIGRATE",
            "source": "edge-hot",
            "destination": "edge-cool",
            "label": "Migrate hot -> cool",
        },
        {
            "type": "MIGRATE",
            "source": "edge-hot",
            "destination": "edge-stale",
            "label": "Migrate hot -> stale",
        },
    ]
    results = evaluate_candidates(
        twin,
        actions,
        service_cpu=0.6,
        service_mem_mb=768.0,
        service_rate=120.0,
        state_mb=128.0,
        bandwidth_mbps=200.0,
    )
    return twin, actions, results


def _kubectl_json(args: list[str], kubeconfig: str | None) -> dict:
    command = ["kubectl"]
    if kubeconfig:
        command.extend(["--kubeconfig", kubeconfig])
    command.extend(args)
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("kubectl was not found; install it and ensure it is on PATH") from exc
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown kubectl error"
        raise RuntimeError(f"{' '.join(command)} failed: {detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"kubectl returned invalid JSON for {' '.join(args)}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"kubectl returned an unexpected response for {' '.join(args)}")
    return value


def _quantity(value: str, *, cpu: bool) -> float:
    """Convert a Kubernetes CPU quantity to cores or memory quantity to bytes."""
    match = re.fullmatch(
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]*)", str(value)
    )
    if not match:
        raise ValueError(f"unsupported Kubernetes quantity: {value!r}")
    number = float(match.group(1))
    suffix = match.group(2)
    if cpu:
        factors = {"": 1.0, "n": 1e-9, "u": 1e-6, "m": 1e-3}
        if suffix not in factors:
            raise ValueError(f"unsupported CPU quantity suffix: {suffix!r}")
        return number * factors[suffix]
    factors = {
        "": 1.0,
        "k": 1e3,
        "K": 1e3,
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
        "P": 1e15,
        "E": 1e18,
        "Ki": 1024.0,
        "Mi": 1024.0**2,
        "Gi": 1024.0**3,
        "Ti": 1024.0**4,
        "Pi": 1024.0**5,
        "Ei": 1024.0**6,
    }
    if suffix not in factors:
        raise ValueError(f"unsupported memory quantity suffix: {suffix!r}")
    return number * factors[suffix]


def _fetch_cluster_snapshot(
    kubeconfig: str | None, *, wait_for_metrics: bool
) -> tuple[list, dict]:
    """Read Node objects plus the metrics.k8s.io node usage list via kubectl.

    One-shot mode waits for metrics-server samples; a live-feed tick makes a
    single attempt and lets the caller retry on the next tick.
    """
    nodes_response = _kubectl_json(["get", "nodes", "-o", "json"], kubeconfig)
    node_items = nodes_response.get("items", [])
    if not node_items:
        raise RuntimeError("the Kubernetes API returned no nodes")
    detail = "unknown metrics error"
    attempts = 12 if wait_for_metrics else 1
    for attempt in range(attempts):
        try:
            metrics_response = _kubectl_json(
                ["get", "--raw", "/apis/metrics.k8s.io/v1beta1/nodes"], kubeconfig
            )
            metrics_by_name = {
                item.get("metadata", {}).get("name"): item
                for item in metrics_response.get("items", [])
            }
            missing = [
                item.get("metadata", {}).get("name", "<unnamed>")
                for item in node_items
                if item.get("metadata", {}).get("name") not in metrics_by_name
            ]
            if not missing:
                return node_items, metrics_by_name
            detail = "metrics.k8s.io has no usage sample for node(s): " + ", ".join(missing)
        except RuntimeError as exc:
            detail = str(exc)
            if "ServiceUnavailable" not in detail and "server is currently unable" not in detail:
                raise
        if attempt == attempts - 1:
            raise RuntimeError(detail + "; ensure metrics-server is running and retry")
        time.sleep(5)
    raise RuntimeError(detail)


def _current_context(kubeconfig: str | None) -> str:
    try:
        context_response = subprocess.run(
            [
                "kubectl",
                *( ["--kubeconfig", kubeconfig] if kubeconfig else [] ),
                "config",
                "current-context",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("kubectl was not found; install it and ensure it is on PATH") from exc
    return context_response.stdout.strip() if context_response.returncode == 0 else "current context"


def _twin_from_snapshot(node_items: list, metrics_by_name: dict) -> TwinState:
    """Build the Digital Twin from one Node + metrics.k8s.io snapshot."""
    twin = TwinState(stale_after_seconds=120.0)
    for item in node_items:
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        if not name:
            continue
        status = item.get("status", {})
        allocatable = status.get("allocatable", {})
        capacity = status.get("capacity", {})
        cpu_total = _quantity(allocatable.get("cpu", capacity.get("cpu", "0")), cpu=True)
        mem_total_mb = (
            _quantity(allocatable.get("memory", capacity.get("memory", "0")), cpu=False)
            / (1024.0**2)
        )
        metric = metrics_by_name[name]
        usage = metric.get("usage", {})
        cpu_used = _quantity(usage.get("cpu", "0"), cpu=True)
        mem_used_mb = _quantity(usage.get("memory", "0"), cpu=False) / (1024.0**2)
        timestamp_text = metric.get("timestamp")
        if not timestamp_text:
            raise RuntimeError(f"metrics.k8s.io sample for node {name} has no timestamp")
        try:
            timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise RuntimeError(f"invalid metrics timestamp for node {name}: {timestamp_text!r}") from exc
        conditions = status.get("conditions", [])
        ready = next((condition for condition in conditions if condition.get("type") == "Ready"), None)
        health = "healthy" if ready and ready.get("status") == "True" else "unhealthy"
        if cpu_total <= 0 or mem_total_mb <= 0:
            raise RuntimeError(f"node {name} has invalid allocatable CPU or memory")
        twin.apply_telemetry(
            name,
            min(1.0, cpu_used / cpu_total),
            min(1.0, mem_used_mb / mem_total_mb),
            cpu_total=cpu_total,
            memory_total_mb=mem_total_mb,
            health=health,
            timestamp=timestamp,
        )
    return twin


def build_cluster_demo(kubeconfig: str | None) -> tuple[TwinState, list[dict], list[dict], str]:
    """Read Node and metrics.k8s.io APIs through kubectl; never writes to Kubernetes."""
    node_items, metrics_by_name = _fetch_cluster_snapshot(kubeconfig, wait_for_metrics=True)
    twin = _twin_from_snapshot(node_items, metrics_by_name)
    context = _current_context(kubeconfig)
    actions, results = _tick_actions(twin)
    # No independent, scope-matched reference stream is available. Leave fidelity
    # at zero so the safety gate fails closed for non-NOOP actions.
    return twin, actions, results, context


def _verdicts(
    twin: TwinState, actions: list[dict], results: list, prediction_confidence: float = 0.92
) -> list[dict]:
    gate = SafetyGate()
    verdicts = []
    for action, result in zip(actions, results):
        if not result.feasible:
            verdicts.append({"approved": False, "reasons": ["counterfactual simulation is infeasible"]})
            continue
        source = twin.get_node(action.get("source", ""))
        destination = twin.get_node(action.get("destination", ""))
        # The gate's fidelity threshold is the available freshness/fidelity
        # control. A stale node is represented as zero fidelity for this check.
        fidelity = min(
            (source.fidelity if source and not source.stale else 0.0),
            (destination.fidelity if destination and not destination.stale else 1.0),
        )
        if (source and source.stale) or (destination and destination.stale):
            fidelity = 0.0
        verdict = gate.evaluate(
            {
                "action": action,
                "predicted": {
                    "slo_violation_probability": result.slo_violation_prob,
                    "prediction_confidence": prediction_confidence,
                },
                "dt_fidelity": fidelity,
                "source_healthy": bool(source and source.health == "healthy" and not source.stale),
                "destination_healthy": bool(destination and destination.health == "healthy" and not destination.stale),
                "destination_free_cpu": (destination.cpu_total - destination.cpu_used) if destination else 0,
            }
        )
        verdicts.append({"approved": verdict.approved, "reasons": verdict.reasons})
    return verdicts


def _colored(text: str, code: str, enabled: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if enabled else text


# -- live feed: manifest, forecasts, rendering -------------------------------


def _manifest(source: str, models: list[str]) -> dict:
    """Explicit inventory of what the local demo simulation runs - and does not."""
    common = [
        "Digital Twin (services/simulation-service app.twin.TwinState: sync, staleness, fidelity)",
        f"Forecast models (services/prediction-service prediction_app.models.py): {', '.join(models)}",
        "Counterfactual simulator (app.simulator: migrate/scale/no-op cost + latency + SLO)",
        "Safety / policy gate (app.safety.SafetyGate): fail-closed, no actuation",
    ]
    if source == "kubernetes":
        host_container = [
            "Docker daemon on this machine (hosts only this demo container)",
            "k3d cluster 'dt-ram': server-0 (cloud control plane), agent-0/agent-1 (edge nodes), serverlb, metrics-server",
        ]
        in_process = ["Read-only kubectl calls: Node objects, metrics.k8s.io usage, current context", *common]
    else:
        host_container = ["None: the whole demo runs inside this python process (no Docker/Kubernetes part)"]
        in_process = ["Seeded synthetic fixture generator (build_demo)", *common]
    return {
        "host_container": host_container,
        "in_process": in_process,
        "not_running": [
            "Go services: telemetry-agent, twin-manager, infrastructure-controller",
            "Node.js services: api-gateway, experiment-service",
            "Event buses / stores: NATS JetStream, PostgreSQL, Redis",
            "Monitoring: Prometheus, Grafana",
            "RL/PPO engine and torch-based neural forecast models (not used by this demo)",
            "Kubernetes actuation: the demo never writes to the cluster (shadow-only)",
        ],
    }


def _manifest_lines(manifest: dict) -> list[str]:
    lines = ["RUNNING LOCALLY AS PART OF THIS DEMO SIMULATION:"]
    for section, title in (
        ("host_container", "host/docker"),
        ("in_process", "in this process"),
        ("not_running", "explicitly NOT running (a full DT-RAM deployment would add these; actuation stays off)"),
    ):
        lines.append(f"  {title}:")
        lines.extend(f"    - {entry}" for entry in manifest[section])
    return lines


@dataclass(frozen=True)
class ForecastPoint:
    node_id: str
    metric: str
    model: str
    value: float | None
    mae: float | None
    confidence: float
    status: str  # "ok" | "insufficient history" | "fit failed"


class _ForecastTracker:
    """Rolling next-sample forecasts for node CPU/memory utilization.

    Uses the real prediction-service models on the snapshots collected by the
    feed. When the next sample arrives, the previous tick's forecast is scored
    against it; the rolling mean absolute error yields a measured confidence
    (1 - MAE) that is fed to the safety gate. No fabricated confidence: until
    forecasts have been realized the confidence is 0.0 and the gate fails closed.
    """

    def __init__(self, models: list[str], history: int) -> None:
        self._models = models
        self._history = history
        self._series: dict[tuple[str, str], deque] = {}
        self._errors: dict[tuple[str, str, str], deque] = {}
        self._pending: dict[tuple[str, str], dict[str, float]] = {}

    def observe(self, node_id: str, cpu_util: float, mem_util: float) -> None:
        for metric, value in (("cpu", cpu_util), ("memory", mem_util)):
            series = self._series.setdefault((node_id, metric), deque(maxlen=self._history))
            pending = self._pending.get((node_id, metric))
            if pending is not None:
                for model, predicted in pending.items():
                    key = (node_id, metric, model)
                    self._errors.setdefault(key, deque(maxlen=32)).append(abs(value - predicted))
            series.append(value)

    def forecast(self, node_id: str) -> list[ForecastPoint]:
        rows: list[ForecastPoint] = []
        for metric in FEED_METRICS:
            series = self._series.get((node_id, metric))
            if not series:
                continue
            history = tuple(series)
            point_forecasts: dict[str, float] = {}
            for model in self._models:
                if model != "persistence" and len(history) < _MIN_FORECAST_HISTORY:
                    predicted, status = None, "insufficient history"
                else:
                    try:
                        if model == "persistence":
                            predicted = persistence_model(history, (1,))[0]
                        else:
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore")
                                predicted = statistical_model(model, history, (1,))[0]
                        point_forecasts[model] = predicted
                        status = "ok"
                    except Exception:
                        predicted, status = None, "fit failed"
                errors = self._errors.get((node_id, metric, model))
                if errors:
                    mae = sum(errors) / len(errors)
                    confidence = min(1.0, max(0.0, 1.0 - mae))
                else:
                    mae, confidence = None, 0.0
                rows.append(
                    ForecastPoint(node_id, metric, model, predicted, mae, confidence, status)
                )
            if point_forecasts:
                self._pending[(node_id, metric)] = point_forecasts
        return rows

    def series(self, node_id: str, metric: str) -> deque:
        return deque(self._series.get((node_id, metric), ()))

    def samples(self, node_id: str) -> int:
        return len(self._series.get((node_id, "cpu"), ()))


_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: deque, width: int = 12) -> str:
    if not values:
        return ""
    chars = []
    for value in list(values)[-width:]:
        index = int(min(max(value, 0.0), 0.999) * len(_SPARK_CHARS))
        chars.append(_SPARK_CHARS[index])
    if len(chars) < width:
        chars = [" "] * (width - len(chars)) + chars
    return "".join(chars)


def _tick_actions(twin: TwinState) -> tuple[list[dict], list]:
    """Counterfactual candidates for one feed tick (same shape as --once mode)."""
    healthy = [node for node in twin.list_nodes() if node.health == "healthy" and not node.stale]
    source = max(healthy or twin.list_nodes(), key=lambda node: node.cpu_util)
    destinations = [node for node in healthy if node.node_id != source.node_id]
    actions = [{"type": "NOOP", "source": source.node_id, "label": "Keep current placement"}]
    actions.append(
        {
            "type": "SCALE",
            "source": source.node_id,
            "replicas": 3,
            "label": "Scale illustrative service to 3",
        }
    )
    if destinations:
        destination = min(destinations, key=lambda node: node.cpu_util)
        actions.append({
            "type": "MIGRATE", "source": source.node_id, "destination": destination.node_id,
            "label": f"Migrate illustrative service -> {destination.node_id}",
        })
    results = evaluate_candidates(
        twin,
        actions,
        service_cpu=0.6,
        service_mem_mb=768.0,
        service_rate=120.0,
        state_mb=128.0,
        bandwidth_mbps=200.0,
    )
    return actions, results


def _forecast_cell(row: ForecastPoint, width: int) -> str:
    if row.status != "ok" or row.value is None:
        return f"{row.status:>{width}}" if len(row.status) <= width else f"{'unavailable':>{width}}"
    value = f"{row.value:.2f}" + (f"/{row.mae:.3f}" if row.mae is not None else "/ --- ")
    return f"{value:>{width}}"


def _render_frame(
    *,
    tick: int,
    interval: float,
    context: str,
    twin: TwinState,
    tracker: _ForecastTracker,
    actions: list[dict],
    results: list,
    verdicts: list[dict],
    rows_by_node: dict[str, list[ForecastPoint]],
    models: list[str],
    confidence: float,
    color: bool,
) -> str:
    lines: list[str] = []
    badge = _colored(" SHADOW-ONLY | NO ACTUATION ", "1;37;41", color)
    clock = datetime.now().strftime("%H:%M:%S")
    lines.append(
        f"DT-RAM  {badge}  Kubernetes snapshot | context {context} | "
        f"{_colored('LIVE FEED', '1;36', color)} tick {tick} every {interval:g}s | {clock} | "
        "Ctrl+C stops the feed (cluster stays up, nothing is written)"
    )
    lines.append("")
    lines.extend(_manifest_lines(_manifest("kubernetes", models)))
    lines.append("")
    lines.append("DIGITAL TWIN (read-only Node API + metrics.k8s.io, resynced every tick)")
    node_width = max(14, *(len(node.node_id) for node in twin.list_nodes()))
    lines.append(
        f"{'NODE':<{node_width}} {'CPU':>7} {'MEM':>7} {'CPU HIST':>12} {'FIDELITY':>10} {'SAMPLES':>8}  STATUS"
    )
    for node in twin.list_nodes():
        status = "STALE - fail closed" if node.stale else ("NOT READY" if node.health != "healthy" else "healthy")
        status = _colored(status, "1;33" if node.stale or node.health != "healthy" else "32", color)
        lines.append(
            f"{node.node_id:<{node_width}} {node.cpu_util:>6.1%} {node.mem_util:>6.1%} "
            f"{_sparkline(tracker.series(node.node_id, 'cpu')):>12} {node.fidelity:>10.3f} "
            f"{tracker.samples(node.node_id):>8}  {status}"
        )

    lines.append("")
    lines.append(
        "FORECASTS (prediction_app models in this process; VALUE/rolling-MAE per model,"
        " next sample ~= tick interval; CONF = 1 - MAE, 0 until forecasts are realized)"
    )
    model_header = "".join(f"{model:>18}" for model in models)
    lines.append(f"{'NODE':<{node_width}} {'METRIC':<7} {'SAMPLES':>8} {model_header} {'CONF':>6}")
    for node in twin.list_nodes():
        rows = rows_by_node.get(node.node_id, [])
        for metric in FEED_METRICS:
            metric_rows = [row for row in rows if row.metric == metric]
            if not metric_rows:
                continue
            cells = "".join(_forecast_cell(row, 18) for row in metric_rows)
            confidence_here = min(
                (row.confidence for row in metric_rows if row.value is not None), default=0.0
            )
            lines.append(
                f"{node.node_id:<{node_width}} {metric:<7} {tracker.samples(node.node_id):>8} "
                f"{cells} {confidence_here:>6.3f}"
            )

    lines.append("")
    lines.append("COUNTERFACTUALS -> SAFETY GATE (per-tick candidates; shadow-only)")
    candidate_width = max(27, *(len(action["label"]) for action in actions))
    lines.append(
        f"{'CANDIDATE':<{candidate_width}} {'SIM':<9} {'CPU':>6} {'MEM':>6} {'P95*':>7} "
        f"{'SLO P':>7} {'MIG COST':>9} {'GATE':<10}"
    )
    for action, result, verdict in zip(actions, results, verdicts):
        sim = "feasible" if result.feasible else "blocked"
        gate = _colored(
            "APPROVED" if verdict["approved"] else "DENIED",
            "32" if verdict["approved"] else "1;31",
            color,
        )
        lines.append(
            f"{action['label']:<{candidate_width}} {sim:<9} {result.predicted_cpu:>5.1%} "
            f"{result.predicted_mem:>5.1%} {result.predicted_latency_ms:>6.1f} "
            f"{result.slo_violation_prob:>6.1%} {result.migration_cost:>9.2f} {gate}"
        )
        if not verdict["approved"]:
            lines.extend(f"  - {reason}" for reason in verdict["reasons"])
        elif result.action_type == "MIGRATE":
            lines.append(f"  - migration duration: {result.migration_duration_s:.2f}s")
    lines.append("")
    lines.append(
        "* CPU/memory are live metrics-server samples; latency and SLO probability are simulator estimates."
    )
    lines.append(
        f"  Twin fidelity is 0 (no independent reference stream), so non-NOOP verdicts fail closed."
    )
    lines.append(
        f"  Gate prediction confidence {confidence:.3f} is measured from the feed's realized forecasts"
        " (rolling MAE); 0 until measured."
    )
    return "\n".join(lines)


def run_live(args: argparse.Namespace, color: bool) -> int:
    """Continuous shadow-only feed; repaints a frame every --interval seconds."""
    models = available_forecast_models()
    tracker = _ForecastTracker(models, args.history)
    print("DT-RAM live feed: starting local simulation components (twin, forecast models,")
    print("simulator, safety gate). First tick reads the snapshot; Ctrl+C stops the feed.", flush=True)
    repaint = color
    if repaint:
        sys.stdout.write("\033[H\033[2J")
        sys.stdout.flush()
    tick = 0
    failures = 0
    while args.ticks == 0 or tick < args.ticks:
        started = time.monotonic()
        try:
            node_items, metrics_by_name = _fetch_cluster_snapshot(args.kubeconfig, wait_for_metrics=False)
            twin = _twin_from_snapshot(node_items, metrics_by_name)
            twin.refresh_staleness()
            context = _current_context(args.kubeconfig)
            actions, results = _tick_actions(twin)
            for node in twin.list_nodes():
                tracker.observe(node.node_id, node.cpu_util, node.mem_util)
            rows_by_node = {node.node_id: tracker.forecast(node.node_id) for node in twin.list_nodes()}
            # Gate confidence = the current tick's measured forecast confidence
            # (minimum across models/metrics; 0 while any current model row
            # lacks a realized forecast). computed from rows_by_node only.
            measured = [
                row.confidence
                for rows in rows_by_node.values()
                for row in rows
                if row.value is not None
            ]
            confidence = min(measured, default=0.0)
            verdicts = _verdicts(twin, actions, results, prediction_confidence=confidence)
            frame = _render_frame(
                tick=tick + 1,
                interval=args.interval,
                context=context,
                twin=twin,
                tracker=tracker,
                actions=actions,
                results=results,
                verdicts=verdicts,
                rows_by_node=rows_by_node,
                models=models,
                confidence=confidence,
                color=color,
            )
            failures = 0
        except (RuntimeError, ValueError) as exc:
            failures += 1
            note = (
                f"tick {tick + 1} failed ({failures}/{MAX_CONSECUTIVE_TICK_FAILURES} consecutive): "
                f"{exc}; retrying next tick"
            )
            if repaint:
                sys.stdout.write(f"\033[H\033[J{note}\n")
                sys.stdout.flush()
            else:
                print(f"DT-RAM: {note}", flush=True)
            if failures >= MAX_CONSECUTIVE_TICK_FAILURES:
                print("DT-RAM live feed: too many consecutive tick failures; stopping.", file=sys.stderr)
                return 2
            time.sleep(args.interval)
            continue
        if repaint:
            sys.stdout.write(f"\033[H\033[J{frame}\n")
        else:
            print(f"\n---- tick {tick + 1} ----\n{frame}\n", flush=True)
        tick += 1
        elapsed = time.monotonic() - started
        if args.ticks == 0 or tick < args.ticks:
            time.sleep(max(0.2, args.interval - elapsed))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", help="kubeconfig path (otherwise kubectl uses KUBECONFIG/current context)")
    parser.add_argument("--synthetic", action="store_true", help="use the built-in synthetic fixture instead of Kubernetes")
    parser.add_argument("--seed", type=int, default=42, help="synthetic fixture seed (default: 42)")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("--json", action="store_true", help="print results as JSON (implies --once)")
    parser.add_argument("--live", action="store_true", help="continuous shadow-only feed (the demo launchers add this by default)")
    parser.add_argument("--once", action="store_true", help="print a single snapshot and exit (overrides --live)")
    parser.add_argument("--interval", type=float, default=5.0, help="live-feed tick interval in seconds (>= 1)")
    parser.add_argument("--ticks", type=int, default=0, help="number of live ticks to run (0 = until Ctrl+C)")
    parser.add_argument("--history", type=int, default=120, help="snapshots kept per node metric for forecasting (13-600)")
    args = parser.parse_args()
    color = not args.no_color and "NO_COLOR" not in os.environ and sys.stdout.isatty()
    args.interval = max(1.0, args.interval)
    args.ticks = max(0, args.ticks)
    args.history = min(600, max(13, args.history))

    live = args.live and not (args.once or args.json or args.synthetic)
    if live:
        try:
            return run_live(args, color)
        except KeyboardInterrupt:
            print("\nDT-RAM live feed stopped (Ctrl+C); shadow-only, no Kubernetes change was made.")
            return 0
        except (RuntimeError, ValueError) as exc:
            print(f"DT-RAM live feed failed: {exc}", file=sys.stderr)
            return 2

    if args.synthetic:
        twin, actions, results = build_demo(args.seed)
        mode = "synthetic"
        context = None
    else:
        try:
            twin, actions, results, context = build_cluster_demo(args.kubeconfig)
        except (RuntimeError, ValueError) as exc:
            print(f"DT-RAM Kubernetes snapshot failed: {exc}", file=sys.stderr)
            return 2
        mode = "kubernetes"
    verdicts = _verdicts(
        twin, actions, results, prediction_confidence=0.0 if mode == "kubernetes" else 0.92
    )
    if args.json:
        print(
            json.dumps(
                {
                    "mode": "shadow-only",
                    "source": mode,
                    "context": context,
                    "seed": args.seed if args.synthetic else None,
                    "components": _manifest(mode, available_forecast_models()),
                    "nodes": [
                        {
                            "id": n.node_id,
                            "cpu_pct": round(n.cpu_util * 100, 1),
                            "memory_pct": round(n.mem_util * 100, 1),
                            "fidelity": round(n.fidelity if not n.stale else 0.0, 3),
                            "stale": n.stale,
                        }
                        for n in twin.list_nodes()
                    ],
                    "fidelity_note": (
                        "No independent, scope-matched reference stream is available; fidelity is zero, "
                        "and no measured prediction confidence is available, so the safety gate fails "
                        "closed for non-NOOP actions."
                        if mode == "kubernetes" else None
                    ),
                    "candidates": [
                        {
                            "action": action["label"],
                            "simulation": {
                                "feasible": result.feasible,
                                "cpu_pct": round(result.predicted_cpu * 100, 1),
                                "memory_pct": round(result.predicted_mem * 100, 1),
                                "latency_ms": round(result.predicted_latency_ms, 1),
                                "slo_violation_probability": round(result.slo_violation_prob, 4),
                                "migration_cost": round(result.migration_cost, 3),
                                "migration_duration_s": round(result.migration_duration_s, 2),
                            },
                            "safety": verdict,
                        }
                        for action, result, verdict in zip(actions, results, verdicts)
                    ],
                },
                indent=2,
            )
        )
        return 0

    badge = _colored(" SHADOW-ONLY | NO ACTUATION ", "1;37;41", color)
    source_label = (
        f"Kubernetes snapshot | context {context}"
        if mode == "kubernetes"
        else f"synthetic demo | seed {args.seed}"
    )
    print(f"DT-RAM  {badge}  {source_label}")
    print("Candidate actions are simulated and checked; none are sent to infrastructure.\n")
    for line in _manifest_lines(_manifest(mode, available_forecast_models())):
        print(line)
    print()
    if mode == "kubernetes":
        print("DIGITAL TWIN (read-only Node API + metrics.k8s.io snapshot)")
        print("Network metrics and model confidence are unavailable; fidelity/confidence are 0.")
        print("The safety gate therefore fails closed for non-NOOP actions.")
    else:
        print("DIGITAL TWIN (synthetic fixture; fidelity compared with independent synthetic samples)")
    node_width = max(14, *(len(node.node_id) for node in twin.list_nodes()))
    print(f"{'NODE':<{node_width}} {'CPU':>7} {'MEM':>7} {'FIDELITY':>10}  STATUS")
    for node in twin.list_nodes():
        status = "STALE - fail closed" if node.stale else ("NOT READY" if node.health != "healthy" else "healthy")
        if mode == "synthetic" and node.node_id == "edge-hot" and not node.stale:
            status = "HOT"
        status = _colored(status, "1;33" if node.stale or node.health != "healthy" or status == "HOT" else "32", color)
        effective_fidelity = node.fidelity if not node.stale else 0.0
        print(f"{node.node_id:<{node_width}} {node.cpu_util:>6.1%} {node.mem_util:>6.1%} {effective_fidelity:>10.3f}  {status}")

    print("\nCOUNTERFACTUALS -> SAFETY GATE")
    candidate_width = max(27, *(len(action["label"]) for action in actions))
    print(f"{'CANDIDATE':<{candidate_width}} {'SIM':<9} {'CPU':>6} {'MEM':>6} {'P95*':>7} {'SLO P':>7} {'MIG COST':>9} {'GATE':<10}")
    for action, result, verdict in zip(actions, results, verdicts):
        sim = "feasible" if result.feasible else "blocked"
        gate = "APPROVED" if verdict["approved"] else "DENIED"
        gate = _colored(gate, "32" if verdict["approved"] else "1;31", color)
        print(
            f"{action['label']:<{candidate_width}} {sim:<9} {result.predicted_cpu:>5.1%} "
            f"{result.predicted_mem:>5.1%} {result.predicted_latency_ms:>6.1f} "
            f"{result.slo_violation_prob:>6.1%} {result.migration_cost:>9.2f} {gate}"
        )
        if not verdict["approved"]:
            for reason in verdict["reasons"]:
                print(f"  - {reason}")
        elif result.action_type == "MIGRATE":
            print(f"  - migration duration: {result.migration_duration_s:.2f}s")
    if mode == "kubernetes":
        print("\n* CPU/memory are live metrics-server node samples. Candidate workload size and latency are illustrative.")
        print("  Safety verdicts are shadow-only; no Kubernetes resources are changed.")
    else:
        print("\n* Simulator latency estimate. Safety verdicts are illustrative; this demo is shadow-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
