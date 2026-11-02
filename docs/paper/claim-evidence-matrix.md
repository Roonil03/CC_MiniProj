# DT-RAM claim–evidence matrix

Prepared after repository review and independent code, results, method, cloud integration, and academic audits. The matrix describes evidence present in the current checkout; it does not claim fresh execution of historical test reports.

| Candidate claim | Evidence | Status and permitted wording |
|---|---|---|
| DT-RAM implements a modular shadow-mode control architecture | Gateway/controller code; Compose and Kubernetes manifests; testbed findings | **Supported with scope.** The testbed deployed the Go telemetry/twin/controller path with NATS and Redis. The full Compose graph was not demonstrated as an integrated running deployment. |
| The Go telemetry pipeline worked in k3d | Deployment findings and checksummed 5,004-event capture; independent results audit | **Supported.** Telemetry traversed agent → JetStream → twin/collector in a local k3d Docker/WSL2 environment. |
| The experiment used three independent edge nodes | Capture metadata says host-scoped CPU/memory shared among k3d nodes; metrics-server showed different node values | **Contradicted.** Call this a three-node k3d testbed with shared-host measurement scope. Fidelity was zero. |
| The safety path rejected an unsafe/low-fidelity shadow action | Testbed report records synthetic SCALE request, fidelity 0, HTTP 422, `approved=false`, `executed=false` | **Supported narrowly.** This is one shadow rejection; it does not establish general safety guarantees or a complete gateway-to-controller policy evaluation. |
| DT-RAM performs forecast-conditioned counterfactual resource management | Gateway forwards forecast context; simulation code does not use forecast values in state dynamics | **Unsupported by implementation.** Describe the simulator as a simplified candidate-evaluation scaffold; explicitly say forecasts do not condition its dynamics. |
| DT-RAM has a validated PPO resource-management policy | PPO wrapper exists; synthetic environment updates only first CPU value with fixed effects; no training results; historical tests did not exercise SB3 construction/training | **Unsupported.** PPO is an opt-in baseline scaffold, not an evaluated policy. |
| Temporal convolution is the best model | Stored metrics: mean validation RMSE 0.013083 (lowest); GRU test RMSE 0.016219 (lowest); test not for selection | **Supported only as validation-selected for this trace.** Do not claim significant general superiority. |
| Forecast confidence/intervals are calibrated | Three residuals per model per horizon, null interval coverage, unavailable confidence; time samples are autocorrelated and share a host | **Contradicted.** State intervals and confidence unavailable; no distribution-free coverage guarantee is established for this trace; no activation recommendation. |
| Prediction latency is below 100 ms in deployment | Host benchmark direct p95 0.180 ms; in-process API p95 16.199 ms; no live network or target edge measurements | **Supported only as local host software timing.** Avoid deployed or edge latency claim. |
| DT-RAM improves SLO, latency, utilization, migration count, or cost | No workload trace, no app metrics, no policy baseline results, no ablation | **No evidence.** These are proposed future measurements. |
| DT + RL for edge management is novel | Chen et al. (MASS 2023) and Cheng et al. (IEEE Network) already cover DT/RL resource allocation or offloading | **Contradicted as broad novelty.** Frame current paper as an implementation/evidence report; any narrower novelty requires systematic literature comparison. |
| Full cloud stack ran together in Kubernetes | K3d report covers Go/infrastructure subset; no deployed gateway, prediction service, simulator, safety service, or PPO experiment reported | **Unsupported.** Separate configured/scaffolded components from the recorded deployment. |

## Provenance and checks

- Current repository commit observed: `8083b49` (merge of PR #9); worktree was clean during review.
- Forecast artifacts identify evaluation commit `bb4764672d08d6d9d82a5d785be058cda4c467a6` and a clean tree at run time.
- Dataset manifest SHA-256: `acbbdfed5414a141d186c215bc95bc9dbb6179d228c783609377e8a0d9931f4f`.
- Independent audit recomputed four-horizon average RMSE values and confirmed three calibration residuals per model per horizon.
- No tests or experiments were rerun for this paper preparation stage. Historical member logs are labeled as reported results, not fresh verification.

## Research framing

The defensible framing is: **a modular shadow-mode resource-management prototype, a recorded local k3d telemetry integration, and a preliminary seven-model CPU forecasting comparison on a short idle trace**. It is not a validated DT-RL controller or a comparative resource-management effectiveness study.
