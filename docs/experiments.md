# Experimental Design & Benchmark Protocol

Evaluation metrics include SLOVR, CDA, Decision Regret, and baseline comparisons.

## Offline Model run

`scripts/run_dt_models.ps1` is an opt-in PowerShell 5.1/7 wrapper around the
existing prediction sweep and RL CLI. A real run requires Docker Desktop in
Linux-container mode, an NVIDIA GPU accessible to Docker, and a configured
local `.env`. No Python installation on Windows is needed: preparation,
training, estimates, and plotting run inside the GPU-enabled prediction
container (currently Python 3.11). It builds/starts the Compose prediction service and its dependencies with
`docker-compose.gpu.yml`, then verifies CUDA in the prediction container. It
installs the optional pinned PPO dependencies in the prediction container.
CUDA-enabled PyTorch is installed in the image during its build. Docker Desktop and GPU drivers are
prerequisites; the script does not install those host components. Docker image
and pinned package pulls are required on first setup. The default input is
Bitbrains fastStorage: the runner downloads it when it is not cached. Supply
`-TelemetryExport` for local `NODE_METRIC_UPDATED` JSONL, or explicitly pass
`-UseBitbrains:$false` without an export to generate synthetic fixtures. The
input manifest records source identity; prepared SQLite inputs can be included
in the output ZIP, so inspect the archive before sharing.

From the repository root, inspect the plan with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_dt_models.ps1 -WhatIf -UseBitbrains:$false -RunId example-synthetic -Models persistence -Scenarios stable -Seeds 42
```

For an actual local GPU run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_dt_models.ps1 -UseBitbrains:$false -RunId example-synthetic -Scenarios stable,burst -Seeds 42,43 -CheckpointPackage
```

Add `-Policies ppo` only when optional simulation training is desired. The
statistical baselines (ARIMA/ETS) use CPU because their existing statsmodels
implementation has no CUDA path. Neural forecasting and PPO require CUDA in
this runner; they fail rather than silently falling back to CPU. The prediction
service and its NATS dependency are started, while the
offline sweep uses only local SQLite data and never consumes live broker
messages. The
script starts with a bounded persistence calibration and records an estimate
before the sweep. The estimate is low confidence for statistical and neural
models until measured timings exist; ARIMA and ETS refit repeatedly and can
take substantially longer. The Python sweep records UTC events, epoch losses,
system snapshots, per-job state, metrics, plots, failures and model artifacts.
Resume with the same arguments and run ID; the runner skips completed jobs and
retries interrupted or failed jobs. `-Fresh` requires a new run ID to preserve
prior outputs. The final `experiments/runs/windows-models/<RunId>.zip` contains
the run manifest, configs, logs, JSON, plots and resumable artifacts. The
prepared input is stored at `<RunId>/<scenario-seed>/input.sqlite` inside the run directory and included in the ZIP. Run data and model weights remain Git-ignored. Synthetic results show software behavior only. With `-UseBitbrains`, see the [real-trace guide](real-trace-run.md), the [completed bitbrains-02 report](analysis/bitbrains-02-2026-11-15.md), and the [earlier partial bitbrains-01 report](analysis/bitbrains-01-partial-2026-11-15.md).

### Recorded synthetic example: trial-01

On 2026-11-11, `trial-01` completed stable and burst synthetic CPU forecasting
scenarios with seeds 42 and 43. The seven-model sweep completed all jobs, but
each generated fixture contains only one synthetic node and 1,800 samples.
The comparison is an offline runner and metric-path check, not a real-cluster
benchmark or research result. The run metadata reports a dirty working tree
and unavailable commit identifiers in per-model records;. The saved
interval results have one calibration sample per horizon, so uncertainty
calibration and coverage are unavailable. See the [sanitized trial report](analysis/trial-01-synthetic-forecasting-2026-11-11.md)
for per-seed and per-scenario results, provenance, software versions, and
limitations. The ignored inputs, model artifacts, and raw run outputs remain
local and are not part of the report or Git.

## Optional synthetic policy objectives

The opt-in RL CLI flag `--multi-objective` reports SLA violation rate,
mean latency, an energy proxy (mean squared CPU utilization), migration
count/cost, and reward spread on common held-out seeds. These are simulator
proxies, not measured energy or live SLA outcomes. The reward uses binary SLA
violation, latency divided by 100 ms, migration indicator, mean squared CPU,
cross-node CPU standard deviation, and a non-no-op action indicator, weighted
respectively by 10, 3, 2.5, 1.5, 1.5, and 1. The weights are configurable in
`EnvConfig`; sensitivity should be evaluated by changing one weight at a time
on the same seeds before interpreting a policy ranking. Domain randomization
is separately opt-in. PPO training completion is not policy-quality evidence.

The separate `scripts/run_synthetic_scenarios.py` CLI is opt-in and creates
local JSON fixtures for burst/memory pressure, degraded migration,
telemetry replay, store outage/recovery, correlated failures, confidence
collapse, conflicting constraints, and migration cooldown. Use
`-RunAdversarialScenarios` in the PowerShell runner to include its JSON in
the archive. Each row records assumptions, seed, expected safe behavior,
decision latency and supported metrics. Affinity, data locality, noisy
neighbours and conflicting SLOs remain marked `planned` because the current
state/action contract cannot evaluate them. Recovery time, prediction error
and real energy are unavailable in these local fakes; do not interpret the
fixture timings as performance benchmarks.

For a reproducible runtime comparison, use the same Git SHA, hardware/GPU,
Python/CUDA versions, input hash, seed set, model set, history, horizons and
epoch budget. Run a warm-up and at least three separate run IDs, report the
median and range for fit time, per-horizon inference latency and RSS, and keep
statistical refit counts alongside neural batch counts. The PowerShell
pre-run estimate is a scheduling aid; it is not a performance result.
