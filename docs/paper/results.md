# Research Paper: Results & Discussion

Empirical evaluation, ablation study, and decision regret analysis.

## Forecasting evaluation on recorded k3d telemetry

Seven forecasting approaches were evaluated on 5,004 real node samples from
the three-node k3d testbed using chronological 60/20/20 partitions and 5, 10,
30, and 60 second horizons. Missing one-second buckets were not imputed. The
documented 60-sample history yielded no valid windows, so the comparison used
a 20-sample history and records this deviation explicitly.

The temporal convolution had the lowest mean validation RMSE (0.013083), a
5,021-byte artifact, and 0.072 ms mean test inference latency. Its 200-repeat
direct-inference p95 was 0.209 ms and its in-process API p95 was 14.512 ms on
the 16-logical-CPU Windows testbed host. GRU had the lowest mean test RMSE
(0.016219), but it was not selected from test results.

No model is recommended for activation. The capture contains only an idle
baseline, k3d nodes share one host, target-edge live-network latency was not
measured, and the temporal model's mean held-out 90% interval coverage was
only 51.6%. It is suitable only for further shadow evaluation on a longer,
labeled workload and fault trace. Full tables, metadata, and plots are in
[`experiments/analysis/k3d-20261101-forecasting`](../../experiments/analysis/k3d-20261101-forecasting/README.md).
