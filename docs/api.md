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
| `POST` | `/decisions/approve` | Request safety approval | Safety service |
| `GET` | `/dashboard/summary` | Aggregate read-only dashboard state | Multiple read-only services |

`POST /decisions/approve` never calls Kubernetes or the infrastructure controller. The safety service must approve the decision before an internal event or controlled Go API can actuate it.

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

NATS JetStream remains the asynchronous transport for telemetry, state updates, predictions, decisions, audit logs, and approved actuation events. The Node services do not publish an actuation event until the simulation and safety components define and implement that contract. See [Design.md](../Design.md) Sections 52–54.
