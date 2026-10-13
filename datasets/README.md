# DT-RAM Datasets Directory

This directory stores benchmark workload traces and resource telemetry datasets for training and evaluating DT-RAM forecasting and reinforcement learning models.

## Directory Layout

- `raw/`: Raw external traces (e.g., Alibaba cluster traces, Google cluster trace samples, Azure Functions traces, or custom testbed logs).
  - *Note: Raw datasets are excluded from git tracking via `.gitignore` to prevent repository bloat.*
- `processed/`: Cleaned, resampled, normalized, and partitioned time-series datasets ready for feature engineering and model training.

## Data Ingestion & Preprocessing

When adding new datasets:
1. Place raw traces into `datasets/raw/<dataset_name>/`.
2. Run preprocessing scripts from `services/prediction-service/` or `scripts/`.
3. Save standardized schema outputs into `datasets/processed/`.

## Member 3 node telemetry contract

The implemented Go telemetry agent publishes `NODE_METRIC_UPDATED` events on
`dt.telemetry.node_metric`. Its `timestamp` is an RFC3339 UTC observation time,
`node_id` identifies the physical node, and `metrics` currently contains:

| Field | Unit | Valid range |
|---|---|---|
| `cpu` | fraction of measured node CPU capacity | 0–1 |
| `memory` | fraction of measured node memory capacity | 0–1 |
| `network_in` | Mbit/s | nonnegative |
| `network_out` | Mbit/s | nonnegative |

The predictor records these exact events in a local SQLite database. Events
with the same node and timestamp are idempotent when their values agree;
conflicting duplicates are rejected. Forecast windows use the latest sample
within each configured time bucket. A missing bucket invalidates a window;
future data is never imputed into its history. This database is a Member 3
recording input, not the project's planned TimescaleDB historical event sink.
The `prediction_app.collector export` command produces replayable JSONL and
a sidecar manifest with its content hash, nodes, period, and missing-bucket
counts under `datasets/processed/` when given that output location.

Keep collection details alongside any research dataset: source/testbed,
collection period, node topology, workload/fault schedule, and schema version.
Training also requires a `--source-label` and records the sorted sample hash,
sample count, nodes, time span, seed, Git state, and model configuration.
Raw telemetry, processed data, SQLite files, and model weights remain ignored
by Git. Small fixtures inside tests are for software verification only.

Request rate, application latency, and queue length are design targets, but
they are not present in the implemented node telemetry event. They need an
explicit workload telemetry source before Member 3 can train or claim results
for those targets.
