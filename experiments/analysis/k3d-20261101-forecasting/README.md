# Real k3d CPU forecasting evaluation

## Decision

Do not activate any model. The temporal convolution is the validation-selected
candidate for further shadow evaluation, but this capture is only 30 minutes of
idle k3d telemetry and its node measurements share one Docker/WSL2 host. Only
three per-node, time-spaced calibration residuals were available per horizon.
They are also not independent physical-node evidence because all nodes share
one host. Interval coverage is therefore unavailable, and these results do not
support autonomous resource decisions.

## Data and protocol

- Capture: `k3d-20261101T122151Z-712516d`, 2026-11-01 12:20:47–12:51:04 UTC.
- Source: Go telemetry DaemonSet → NATS JetStream → prediction collector.
- Data: 5,004 verified samples, three nodes, JSONL SHA-256
  `acbbdfed5414a141d186c215bc95bc9dbb6179d228c783609377e8a0d9931f4f`.
- Target: CPU utilization fraction. No application latency, request-rate, SLO,
  workload, or fault labels were available.
- Split: chronological 60/20/20; validation is further separated for tuning,
  interval calibration, and coverage audit. Test origins are shared across all
  models and never used for fitting or calibration.
- Interval status: unavailable. Node-aware spacing retains three per-node
  residuals per horizon, fewer than the nine required even before accounting
  for shared-host correlation; the evaluator refuses a nominal 90% label.
- Horizons: 5, 10, 30, and 60 seconds; seed 42; 20 requested epochs.
- History: 20 one-second buckets. The documented 60-bucket default produced
  zero valid windows because the trace has 55 gaps above 1.5 seconds per node.
  No values were imputed. Twenty buckets retained 486 train, 147 validation,
  and 174 test windows before the shared 64-origin score cap.
- Evaluation commit: `bb4764672d08d6d9d82a5d785be058cda4c467a6`;
  all result records report a clean working tree.
- Software: Python 3.10.11, PyTorch 2.14.1, statsmodels 0.15.0.

Obtain the Teammate 2 handoff bundle named
`k3d-20261101T122151Z-712516d` from the project shared handoff storage and
verify `processed/node-events.jsonl` against the SHA-256 above. The capture is
not committed because repository policy excludes raw and processed datasets.
PR #8 records the handoff archive as
`local-dev/artifacts/k3d-20261101T122151Z-712516d.zip`, SHA-256
`cc9f51bd93a33a1ecbd05fa9e9ab5c97b660003ae32d67845007a2744837a985`;
no durable artifact URL was available at evaluation time.
From `services/prediction-service`, import it and run the comparison:

```text
python -m prediction_app.collector --db data/k3d-20261101.sqlite import <DATASET_ROOT>/k3d-20261101T122151Z-712516d/processed/node-events.jsonl
python -m prediction_app.scripts.run_all_models --db data/k3d-20261101.sqlite --run-dir ../../experiments/runs/k3d-20261101-cpu-h20 --models persistence arima ets lstm gru temporal transformer --metrics cpu --history-steps 20 --horizons 5 10 30 60 --period-seconds 1 --seed 42 --epochs 20 --source-label k3d:k3d-20261101T122151Z-712516d:sha256-acbbdfed5414a141d186c215bc95bc9dbb6179d228c783609377e8a0d9931f4f --max-attempts 1
```

## Comparison

Values are means across the four horizons. Inference latency is the runner's
mean per forecast on the recorded Windows host. Statistical baselines refit at
each origin and do not have a serialized serving artifact.

| Model | Validation RMSE | Test RMSE | Interval coverage | Mean inference ms | Artifact bytes | Run seconds |
|---|---:|---:|---:|---:|---:|---:|
| Persistence | 0.017835 | 0.024384 | unavailable | 0.0003 | n/a | 1.596 |
| ARIMA | 0.014227 | 0.016786 | unavailable | 13.6492 | n/a | 2.733 |
| ETS | 0.014233 | 0.016760 | unavailable | 2.3646 | n/a | 0.487 |
| LSTM | 0.014385 | 0.016749 | unavailable | 0.1560 | 8,429 | 1.860 |
| GRU | 0.013712 | 0.016219 | unavailable | 0.4126 | 7,201 | 0.995 |
| Temporal convolution | **0.013083** | 0.016727 | unavailable | 0.0691 | **5,021** | 0.411 |
| Transformer | 0.013857 | 0.016225 | unavailable | 0.2415 | 17,775 | 0.963 |

The temporal model was selected using validation RMSE before reviewing test
scores. GRU has the lowest mean test RMSE by a negligible margin, but selecting
it from the test partition would be leakage. Most per-horizon R² values are
near zero or negative; the complete per-horizon table is in `metrics.csv`.

## Host latency

The temporal candidate was measured for 200 warm runs on Windows
`10.0.26200`, Intel Family 6 Model 154, with 16 logical CPUs:

| Path | Mean | Median | p95 | Maximum |
|---|---:|---:|---:|---:|
| Direct model inference | 0.106 ms | 0.079 ms | 0.180 ms | 0.394 ms |
| In-process prediction API | 12.824 ms | 12.080 ms | 16.199 ms | 54.449 ms |

Both paths are below the design's 100 ms budget on this host. This is not a
live-network measurement and not a deployment on independent edge hardware;
target-edge latency and server resource use remain unverified.
The observed 9.557-second telemetry gap exceeds the service's default
five-second freshness limit, so a live service would intentionally degrade or
return unavailable during such a gap; this run does not loosen that safety rule.

## Artifacts

- `model-results.json`: complete per-model metadata, metrics, calibration status,
  software versions, dataset hash, and artifact hashes.
- `benchmark-temporal.json`: 200-repeat host latency and process cost.
- `dataset-manifest.json` and `capture-metadata.json`: source provenance and
  known limitations.
- `plots/`: accuracy/coverage, latency/size, neural loss, and runtime figures.

These are real idle-testbed results. Earlier synthetic measurements remain
software checks only and are not used here.
