# DT-RAM validation report

## Scope

This report synthesizes five independent read-only audits (implementation, recorded results, methodology, cloud integration, and academic literature) plus direct inspection of repository artifacts. The working tree was clean before paper artifacts were created. No application tests or experiments were run during validation; historical logs are distinguished from direct artifact checks.

## Independent findings

### Code audit

The Python/Kubernetes boundary is respected in the inspected routes: the gateway targets the safety service, and the Go controller is the Kubernetes mutation boundary. The Go processor currently blocks live requests. The simulator contains simplified CPU/memory feasibility and fixed latency/SLO equations; forecasts do not affect simulated dynamics. The RL environment changes only one CPU value using fixed action relief, and energy/cost reward weights are unused. The PPO wrapper exists, but training is not an evaluated result.

### Recorded result audit

The manifest and deployment report agree on 5,004 events, three node IDs, 1,668 events each, and the dataset digest. Each node has 156 missing buckets among 1,818 within-span buckets (8.58%). Stored validation/test RMSE summaries match calculations from the per-horizon metrics. Each model has three calibration residuals per horizon; interval coverage is null. This autocorrelated, shared-host trace does not establish exchangeability or distribution-free interval coverage. The temporal inference benchmark reports 200 repetitions and in-process HTTP mode. These facts support the narrow results in `main.tex`; they do not support activation, network latency, edge hardware performance, or resource-management benefit.

### Methodology audit

Forecast evaluation uses causal contiguous windows, chronological 60/20/20 partitions, label guard gaps, separate validation tuning/calibration/audit regions, spaced calibration origins, shared score origins, and no test-set model selection. The protocol is more careful than its available data regime: a single short idle trace with gaps and shared-host signals cannot test workload response or cross-node generalization. The raw trace and weights are not checked in, and the referenced external bundle lacks a durable URL.

### Cloud integration audit

The deployment report documents k3d rollout of NATS, Redis, three telemetry agents, twin manager, and infrastructure controller. It records telemetry collection, zero fidelity, dry-run mode, and a rejected low-fidelity shadow request. It does not document deployment of the whole Compose graph or physical edge nodes. The controller has scoped deployment/scale write permissions in the project namespace, while the Go processor and dry-run settings block live actions. Durable audit, restart-safe idempotency, verified migration/placement, and rollback are absent.

### Academic review

Primary publisher and institutional records confirm prior DT-assisted RL resource allocation/offloading (Chen et al.; Cheng et al.), Kubernetes twin work (KubeTwin), cloud-edge microservice DT deployments (Bellavista et al.), migration-cost-aware Kubernetes co-simulation (EdgeBus), dynamic twin placement (Ranjbaran et al.), and forecasting integrated with edge orchestration and deployment (AERO). Therefore, no broad novelty claim for DT+RL, Kubernetes twins, migration cost, or forecast-assisted orchestration is defensible. Reference metadata that could not be confirmed sufficiently was excluded from the paper bibliography.

## Evidence quality and reproducibility limits

The recorded dataset hash and model source/run metadata are useful provenance. But the dataset itself and neural weights are absent from the checkout. The capture report's original base commit, the forecast evaluator commit, and the current merged repository commit differ; the paper reports those as provenance for their respective artifacts rather than implying the evaluated model was produced from the current merge. Historical test reports describe passing suites but are not current-commit reruns. No LaTeX compiler was found on PATH during the environment check, so PDF compilation is unavailable in this session.

## Validation conclusion

The paper's scope is restricted to implementation description, recorded k3d telemetry integration, and preliminary idle-trace forecasting. Statements about forecasting utility in orchestration, twin fidelity, RL performance, safety guarantees, and live actuation are explicitly marked as unsupported or future work.
