# Experimental Design & Benchmark Protocol

Evaluation metrics (SLOVR, CDA, Decision Regret) and baseline comparisons. See [Design.md](../Design.md) Sections 43-50.

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
