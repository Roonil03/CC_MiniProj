# DT-RAM System Architecture

For complete architectural specifications, refer to [Design.md](../Design.md).

## Subsystems

1. **API Gateway & Presentation Layer** (`services/api-gateway/`, `services/experiment-service/`)
2. **Infrastructure & Telemetry Layer** (`services/infrastructure-controller/`, `services/telemetry-agent/`)
3. **Digital Twin State & Simulation Engine** (`services/twin-manager/`, `services/simulation-service/`)
4. **Predictive Analytics & Forecasting Layer** (`services/prediction-service/`)
5. **Reinforcement Learning & Decision Engine** (`services/rl-service/`)
6. **Safety & Policy Gate** (`services/safety-service/`)

## Application boundary

The API gateway validates and authenticates external requests, then delegates
to the owning service. It contains no RL, forecasting, simulation, safety
policy, or Kubernetes logic. Decision requests are normalized at the gateway
boundary; approval obtains twin/prediction context and counterfactual results,
then delegates the canonical safety request. The gateway cannot call the Go
infrastructure controller.

The experiment service owns experiment metadata and persists it in PostgreSQL. Its required provenance fields follow the experiment registry in `Design.md`, while metrics/results remain structured JSON to support different experiment types.

Dashboard aggregation is read-only and reports `degraded` when one or more dependencies are unavailable rather than fabricating state. The safety
service is the only publisher of approved shadow decisions, and the Go
controller remains the only component permitted to perform future Kubernetes
actuation.
