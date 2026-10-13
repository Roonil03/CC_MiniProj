# Research Paper: Methodology

Mathematical formulation of state space, counterfactual simulation, and safety gate.

## Member 3 prediction methodology

The predictor currently uses the Go node metric event as its verified data
contract. Available targets are node CPU and memory utilization fractions and
incoming/outgoing network throughput in Mbit/s. Request rate, latency, and
queue length require additional workload telemetry before they can be
evaluated. Training records source identity, a hash of sorted samples,
collection period, node IDs, model settings, random seed, Git state, and
software versions.

Each candidate predicts selected values 5, 10, 30, and 60 seconds after the
latest observation, using only contiguous past samples. Chronological
train/validation/test partitions are 60/20/20; labels must remain within
their partition. The validation interval is divided again for model tuning,
uncertainty calibration, and coverage assessment. Persistence and ARIMA/ETS
are baselines; LSTM, GRU, and a compact temporal convolution are compared on
the same target definitions. Statistical baselines require per-origin refits.
Tuning and test scores for all models use the same evenly spaced sample of
up to 64 forecast origins. Calibration and audit origins are spaced at least
one maximum forecast horizon apart.

For each target and horizon, report MAE, RMSE, MAPE only where all denominators
are meaningful, and R² only where the target has variance. Report inference
latency, CPU time, RSS, model size, and held-out interval coverage alongside
accuracy. A reported confidence is an approximate lower bound on observed
interval coverage, not the probability that an individual forecast is right.
Correlation between nodes and distribution shifts limit its interpretation.
Stale or uncalibrated forecasts are marked as such and are not evidence for
autonomous control. Research findings require recorded testbed or clearly
identified external traces; software fixtures alone do not establish them.
