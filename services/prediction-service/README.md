# Member 3 prediction service

The service records the Go agent's node telemetry, trains per-metric forecasts,
and serves read-only predictions to the existing API gateway. It has no
Kubernetes client or actuation path. The implemented input subject is
`dt.telemetry.node_metric` (`NODE_METRIC_UPDATED`). The gateway already routes
`GET /predictions` and `GET /models` to port 5000.

## Setup

Use Python 3.11 in an isolated environment. From this directory:

```text
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Use the corresponding `python3` and virtual-environment paths on Linux.
`requirements.txt` is for the runtime image; `requirements-dev.txt` adds the
HTTP test client and benchmark dependency. The repository ignores `.venv/`.

## Record telemetry

The importer accepts one Go node metric event per JSONL line. The listener
uses its own durable JetStream consumer on the existing `DT_TELEMETRY` stream.
It acknowledges a valid event only after the SQLite commit, and terminates
malformed events. A conflicting duplicate remains unacknowledged for operator
investigation.

```text
python -m prediction_app.collector --db data/node_samples.sqlite import path/to/events.jsonl
python -m prediction_app.collector --db data/node_samples.sqlite listen --nats-url nats://localhost:4222
python -m prediction_app.collector --db data/node_samples.sqlite export --output ../../datasets/processed/node-events.jsonl --source-label k3d-node-telemetry-2026-10
```

The current Go agent emits CPU, memory, and network observations. Workload
request rate, latency, and queue depth require a separate verified data source.
The collector does not create missing values for these targets.
The export is replayable JSONL and a sibling manifest containing source,
sample hash, time span, nodes, and missing-bucket counts. Both are ignored
under `datasets/processed/`; keep their versioned copies with experiment
records outside Git when conducting research.

## Train and compare

Run the same command for `persistence`, `arima`, `ets`, `lstm`, `gru`, and
`temporal`, and for each available metric (`cpu`, `memory`, `network_in`,
`network_out`). Example:

```text
python -m prediction_app.training --db data/node_samples.sqlite --output models_saved --source-label k3d-node-telemetry-2026-10 --metric cpu --model persistence
python -m prediction_app.training --db data/node_samples.sqlite --output models_saved --source-label k3d-node-telemetry-2026-10 --metric cpu --model gru --seed 42 --epochs 20
```

Defaults are a 60-sample history at 1-second cadence and 5-, 10-, 30-, and
60-second horizons. `--history-steps`, `--period-seconds`, `--horizons`,
`--seed`, and `--epochs` are explicit experiment parameters. There must be
enough contiguous observations for training, validation, interval calibration,
an independent validation audit, and testing. Training fails if there are not.

The 60/20/20 train/validation/test split follows chronological forecast
origins. Forecast labels stay within their partition. The validation period
is further divided, in order, into tuning, interval calibration, and coverage
audit regions with horizon guard gaps. Calibration and audit origins are
spaced at least one maximum horizon apart. Preprocessing is fitted on training
history only. MAE, RMSE, MAPE when defined, R² when defined, per-horizon
interval coverage, inference time, and artifact size are reported. Shared
tuning and test score origins are capped at the same 64 evenly spaced samples
for every model. ARIMA/ETS also cap calibration and audit origins because
they refit on every history. Training uses all available training windows.
No test partition is used for model fitting or interval calibration.

`models_saved/registry.json` records model version, dataset hash/source/time
span, hyperparameters, scores, software versions, Git SHA and dirty status,
and the artifact hash. Neural weights and local datasets remain ignored by
Git. Review the measured results before selecting a serving model:

```text
python -m prediction_app.registry --registry models_saved/registry.json --model-id MODEL_ID
```

Activation is explicit. The runtime refuses modified or missing neural
artifacts. The statistical refit baselines remain offline because per-request
fitting is unsuitable for the service latency target.

## Serve predictions

```text
python -m uvicorn prediction_app.service:app --host 127.0.0.1 --port 5000
```

Supported settings:

| Setting | Default | Purpose |
|---|---|---|
| `PREDICTION_DATA_PATH` | `data/node_samples.sqlite` | Recorded telemetry |
| `PREDICTION_REGISTRY_PATH` | `models_saved/registry.json` | Model records and sibling `active.json` |
| `PREDICTION_MAX_AGE_SECONDS` | `5` | Maximum age of the latest observation |
| `DT_RAM_SERVICE_TOKEN` | unset | When set, required as `x-service-token` on data routes |

`GET /healthz` reports process liveness. `GET /readyz` requires fresh
telemetry. `GET /models` returns registry records and active selection.
`GET /predictions` returns available node/metric forecasts; optional
`node_id` and `metric` query parameters narrow the result. The gateway's
current route calls it without query parameters. With no active model, a
fresh observed value can produce an explicitly uncalibrated persistence
forecast. No telemetry or entirely stale telemetry yields HTTP 503.

Each forecast includes node, metric, unit, bucket-aligned forecast origin,
latest observation and target timestamps,
horizon, predicted value, optional bounds, model ID, and optional confidence.
`confidence` is an approximate Wilson 95% lower bound of *observed interval coverage*
in a held-out portion of validation, reported only with at least 30 audit
windows. It is not a per-forecast probability of correctness. Correlation
across nodes and distribution drift may invalidate this estimate. Missing
calibration yields `null` confidence;
downstream safety must treat that as insufficient evidence for autonomous
actuation. The predictor never publishes a resource decision.

## Operational benchmark and container

After selecting a model, run:

```text
python -m prediction_app.benchmark --db data/node_samples.sqlite --registry models_saved/registry.json --metric cpu --repeats 50 --output ../../experiments/runs/prediction-benchmark.json
```

The report contains direct inference and HTTP mean/median/p95/max timings,
CPU seconds, process RSS, artifact bytes, host details, dataset version, and
repeat count. It uses recorded observations and their historical timestamp;
freshness and outage behavior are verified separately. The design's
prediction budget is below 100 ms, to be checked on the intended hardware.

The Dockerfile starts the API on port 5000 as a non-root user. Mount writable
`/data` for recorded samples and `/models` for reviewed artifacts, supply the
service token through the deployment environment, and run the collector as a
separate process. This repository does not yet have a verified prediction
service Compose/Kubernetes deployment. Shared stream provisioning, gateway
contract wiring, and RL consumption are integration work.

An optional one-shot publisher proposes `NODE_FORECAST_UPDATED` events on
`dt.predictions.node_forecast` using the same forecast objects as the API.
It has an isolated transport test. That subject is proposed; it is absent
from Member 2's current stream configuration. An integrator must provision
and review the shared subject before this command can publish:

```text
python -m prediction_app.publisher --service-url http://localhost:5000 --nats-url nats://localhost:4222
```

No Python component publishes `RESOURCE_DECISION` or calls Kubernetes.
