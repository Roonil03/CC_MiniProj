# API Specifications & Event Schemas

The API gateway is the public application boundary. Except for `GET /health` and the OpenAPI UI at `/docs`, requests require an `x-api-key` header matching `DT_RAM_API_KEY`.

The gateway communicates with internal services using `DT_RAM_SERVICE_TOKEN`. Do not expose that token to browser clients. Errors from an unavailable or rejecting dependency are returned as `502 Bad Gateway` without exposing credentials.

## Gateway routes

| Method | Route | Purpose | Downstream boundary |
|---|---|---|---|
| `GET` | `/health` | Liveness check | None |
| `GET` | `/configuration` | Non-secret capabilities | None |
| `POST` | `/experiments` | Register an experiment | Experiment service |
| `GET` | `/experiments` | List experiments | Experiment service |
| `GET` | `/experiments/:id` | Read an experiment | Experiment service |
| `PATCH` | `/experiments/:id` | Update status/results/name | Experiment service |
| `DELETE` | `/experiments/:id` | Delete an experiment | Experiment service |
| `GET` | `/nodes` | Query node state | Go infrastructure controller |
| `GET` | `/services` | Query service state | Go infrastructure controller |
| `GET` | `/twin/state` | Query synchronized twin state | Twin manager |
| `GET` | `/predictions` | Query predictions | Prediction service |
| `GET` | `/models` | Query model metadata | Prediction service |
| `GET` | `/policies` | Query safety policies | Safety service |
| `POST` | `/decisions/simulate` | Counterfactually evaluate a candidate | Simulation service |
| `POST` | `/decisions/approve` | Counterfactual-backed shadow approval | Safety service → NATS → Go controller |
| `GET` | `/dashboard/summary` | Aggregate read-only dashboard state | Multiple read-only services |

`POST /decisions/approve` first obtains the current twin and shortest available
forecast through the gateway, evaluates the canonical action in the
simulation service, and sends the simulation-derived prediction, health,
capacity, and fidelity context to the safety service. Client-supplied
prediction and health values are not trusted as authoritative inputs.

Only `executionMode: "shadow"` is available. An approved request is published
to `dt.decisions.resource` with `dry_run: true` and acknowledged by the
JetStream publisher. The Go infrastructure controller consumes and audits the
event, but physical Kubernetes actuation and rollback remain disabled.
`canary` and `controlled` modes return a fail-closed error until those
capabilities are implemented.

## Experiment provenance

Creating an experiment requires `name`, `gitCommit`, `datasetVersion`, `modelVersion`, `configuration`, `environment`, `kubernetesVersion`, `nodeTopology`, `randomSeed`, `rlAlgorithm`, and `hyperparameters`. This enforces the provenance required by the design. New records start with status `created`.

Valid statuses are `created`, `running`, `completed`, `failed`, and `cancelled`. Results are JSON so experiment-specific metrics can be stored without weakening the required provenance fields.

Example:

```json
{
  "name": "burst-workload-ppo",
  "gitCommit": "a8e3c21",
  "datasetVersion": "burst-v1",
  "modelVersion": "ppo-v1",
  "configuration": { "decisionIntervalSeconds": 5 },
  "environment": "simulation",
  "kubernetesVersion": "1.31",
  "nodeTopology": { "edgeNodes": 2, "cloudNodes": 1 },
  "randomSeed": 42,
  "rlAlgorithm": "ppo",
  "hyperparameters": { "gamma": 0.99, "learningRate": 0.0003 }
}
```

## Event schemas

NATS JetStream remains the asynchronous transport for telemetry, predictions,
decisions, and audit/logging contracts. The safety service owns publication of
approved shadow decisions; the Node gateway never publishes or executes an
actuation event. See [Design.md](../Design.md) Sections 52–54.
