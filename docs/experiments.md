# Experimental Design & Benchmark Protocol

Evaluation metrics include SLOVR, CDA, Decision Regret, and baseline comparisons.

## Member 3 forecasting experiment protocol

Collect versioned node telemetry from the implemented Go event contract;
record source, topology, workload schedule, collection interval, and known
faults. Export the replayable JSONL and quality manifest from the prediction
collector. A model run records the dataset hash, seed, configuration, Git
state, software versions, model ID, and artifact hash. Keep large traces,
SQLite recordings, weights, and run output outside Git.

Use the same node entities, target metric, observation cadence, history
length, and horizons for all candidates. Split by time into 60% training,
20% validation, and 20% final testing. Forecast targets must remain inside
their partition. Use the validation period for training decisions and
interval calibration, and select the serving candidate based on validation
error and measured inference cost before interpreting final test scores.

Compare persistence, ARIMA, ETS, LSTM, GRU, the lightweight temporal
convolution, and the lightweight Transformer on per-horizon MAE, RMSE,
defined MAPE and R², and interval coverage.
Measure direct inference and live-network HTTP latency, CPU seconds, process
RSS, and artifact size on named hardware. The in-process HTTP benchmark is a
software check; server resource use requires separate deployment monitoring.
Check the design's prediction latency target of less than 100 ms; report the
measured value even if it misses. Evaluate
stable, periodic, bursty, and fault periods when those labeled observations
exist. Synthetic software fixtures verify behavior only and must never be
reported as testbed research findings.

## Offline Windows model run

`scripts/run_dt_models.ps1` is an opt-in PowerShell 5.1/7 wrapper around the
existing prediction sweep and RL CLI. A real run requires Docker Desktop in
Linux-container mode, Python 3.11, 3.12, or 3.13, an NVIDIA GPU accessible to Docker and Windows Python,
and a configured local `.env`. It builds/starts the local Compose stack with
`docker-compose.gpu.yml`, then verifies CUDA in the prediction container. It
creates `.venv-dt-models` under the repository and installs pinned forecast,
PPO (when requested), and CUDA 12.6 PyTorch wheels there. It never installs
globally or with administrator rights. Docker Desktop and GPU drivers are
prerequisites; the script does not install those host components. It does not
fetch datasets or contact a cluster, cloud, or production service. Docker
image and pinned package pulls are required on first setup.
Without `-TelemetryExport` it prepares deterministic **synthetic** local
fixtures for stable, burst, or memory-pressure forecasting. A supplied export
must be a local `NODE_METRIC_UPDATED` JSONL file. Its raw contents stay outside
the archive; the input manifest records its path and SHA-256 identity.

From the repository root, inspect the plan with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_dt_models.ps1 -WhatIf -RunId trial-01 -Models persistence -Scenarios stable -Seeds 42
```

For an actual local GPU run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_dt_models.ps1 -RunId trial-01 -Scenarios stable,burst -Seeds 42,43 -CheckpointPackage
```

Add `-Policies ppo` only when optional simulation training is desired. The
statistical baselines (ARIMA/ETS) use CPU because their existing statsmodels
implementation has no CUDA path. Neural forecasting and PPO require CUDA in
this runner; they fail rather than silently falling back to CPU. The local
Compose stack is started for the user's requested environment, while the
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
`_inputs` directory holds local SQLite fixtures and is excluded from the ZIP
and Git. Synthetic results show software behavior only.

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
