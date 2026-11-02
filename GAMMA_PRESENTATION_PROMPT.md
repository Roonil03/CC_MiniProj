Create a concise 8-slide academic presentation for a cloud-computing mini-project titled “DT-RAM: A Shadow-Mode Edge–Cloud Resource-Management Prototype and Preliminary Telemetry Study.” Use only the paper’s verified claims and results. Visual style: clean IEEE-like technical presentation, restrained blue/gray palette, readable diagrams, minimal text, and clear labels separating implemented, tested, preliminary, and future work.

Slide 1 — Project and research scope: explain DT-RAM as a modular prototype. State plainly that it is not a validated DT-RL controller and that live Kubernetes actuation is disabled.

Slide 2 — Architecture: show telemetry agent (Go) → NATS JetStream → twin manager (Go) → prediction service (Python) → gateway (TypeScript) → simulation and safety services (Python) → shadow decision → Go controller. Mark the controller as dry-run and the live mutation boundary as blocked. Note the complete Compose graph was not demonstrated as one deployed stack.

Slide 3 — Implementation status: summarize gateway/experiment registry, telemetry and twin, forecasting, simulation/safety, and PPO scaffold. Distinguish services deployed in k3d from components that exist in code or Compose only. Note no Python service controls Kubernetes.

Slide 4 — Method: describe the forecasting comparison: seven models, CPU utilization, 5/10/30/60-second horizons, causal contiguous windows, chronological 60/20/20 split, and shared score origins. Explain that the requested 60-sample history yielded no windows, so 20 samples were used without imputation.

Slide 5 — Testbed and data: show the local k3d topology (one server, two agents on a shared Docker/WSL2 host), 5,004 telemetry events across about 30 minutes, idle/no-fault schedule, 8.58% missing one-second buckets, maximum gap 9.557 seconds, and twin fidelity 0. Explicitly say this is not a three-independent-node physical edge evaluation.

Slide 6 — Actual forecasting results: table the four-horizon mean RMSE (CPU-fraction units): persistence validation/test 0.017835/0.024384; ARIMA 0.014227/0.016786; ETS 0.014233/0.016760; LSTM 0.014385/0.016749; GRU 0.013712/0.016219; temporal convolution 0.013083/0.016727; Transformer 0.013857/0.016225. Temporal convolution was selected by validation RMSE; GRU has lowest test RMSE but was not selected using test data. State the ranking is preliminary and not statistically significant.

Slide 7 — Performance and limitations: temporal model direct inference p95 0.180 ms and in-process API p95 16.199 ms on the capture host; artifact 5,021 bytes. These are not live-network or edge-device benchmarks. Interval coverage is unavailable (three calibration residuals per horizon). No model is approved for activation. Forecasts do not affect simulator dynamics; PPO environment is a simplified scaffold; no resource-management gains are measured.

Slide 8 — Conclusion and next work: the verified contribution is a shadow-mode telemetry integration plus preliminary idle-trace forecast comparison. Next: collect node-specific workload/fault/SLO traces, validate twin and simulator against independent outcomes, implement meaningful forecast-conditioned RL transitions, compare against heuristics with repeated seeds and ablations, and retain shadow mode until rollback and actuation checks are validated.

Do not invent charts, confidence intervals, SLO improvements, RL outcomes, deployment results, literature novelty, or live actuation. Include source labels in speaker notes or small footers for the testbed findings and forecasting analysis.
