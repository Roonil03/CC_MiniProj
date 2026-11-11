# DT-RAM API and event reference

This document describes interfaces implemented in this repository. The public
entry point is the Node.js API gateway. Go and Python HTTP endpoints are
internal service interfaces. The control path remains telemetry → twin →
prediction → simulation → safety → Go controller → Kubernetes. Python services
do not control Kubernetes.

## Access and errors

The gateway listens on port 3000 by default. All application routes except
`GET /health` require `x-api-key: <DT_RAM_API_KEY>`. An unset server key returns
503; a missing or incorrect client key returns 401. The gateway exposes
Swagger UI at `/docs`. It sends `x-service-token` to upstream services when
`DT_RAM_SERVICE_TOKEN` is configured, sets JSON headers for request bodies,
and applies a five-second upstream timeout. Rejected or unavailable upstream
requests return gateway 502. `GET /dashboard/summary` instead reports each
unavailable source and sets its overall status to `degraded`.

The experiment service always requires its service token outside `/health`.
The Go twin and controller services and Python prediction, simulation, and
safety services check the token when configured. The telemetry agent has no
HTTP request authentication. Configure internal service access accordingly.

## Public gateway API

All routes below, except `GET /health`, require the API key.

### Health and configuration

| Method and path | Response |
| --- | --- |
| `GET /health` | Gateway liveness. |
| `GET /configuration` | `environment` and `features` flags for experiment registry, counterfactual simulation, safety approval, and direct Kubernetes actuation. The last flag is `false`. |

### Experiments

The gateway forwards these routes to the PostgreSQL-backed experiment service.
Experiment IDs are UUIDs, validated by that service.

| Method and path | Request and response |
| --- | --- |
| `POST /experiments` | Create an experiment; returns a record with UUID, `created` status, null results, and timestamps. |
| `GET /experiments` | List experiment records. |
| `GET /experiments/:id` | Get one record. |
| `PATCH /experiments/:id` | Update optional `name`, `status`, and/or `results`. |
| `DELETE /experiments/:id` | Returns `{ "deleted": true, "id": "<uuid>" }`. |

Create requires `name`, `gitCommit`, `datasetVersion`, `modelVersion`,
`configuration` (object), `environment`, `kubernetesVersion`, `nodeTopology`
(object), `randomSeed` (nonnegative integer), `rlAlgorithm`, and
`hyperparameters` (object). Allowed statuses are `created`, `running`,
`completed`, `failed`, and `cancelled`. `results` is structured JSON.

### State, models, and dashboard

| Method and path | Response and source |
| --- | --- |
| `GET /nodes` | Kubernetes node list from the Go controller. |
| `GET /services` | Kubernetes **pod** list from the Go controller. |
| `GET /twin/state` | `{ "nodes": [...], "workloads": [...] }` from the twin manager. |
| `GET /predictions` | `{ "status": "ok|degraded", "predictions": [...], "errors": [...] }` from the prediction service. |
| `GET /models` | `{ "models": [...] }`, including active-model indicators. |
| `GET /policies` | Safety thresholds, supported actions/modes, and physical actuation capability. |
| `GET /dashboard/summary` | `generatedAt`, overall `status` (`ok` or `degraded`), and `nodes`, `services`, `twin`, `predictions` entries. Each source entry has `status: ok|unavailable` and, when available, `data`. |

A forecast record identifies `node_id`, `metric`, `unit`, observation and
target timestamps, `horizon_seconds`, `value`, optional `lower_bound` and
`upper_bound`, `confidence`, `confidence_basis`, `model_id`, and calibration
`status`.

### Decisions

`POST /decisions/simulate` requires nonempty `decisionId` and `policyVersion`
strings and an `action` object. It accepts an optional `predicted` object. The
gateway fetches twin and forecast context and returns simulation `results`.
It does not execute the action.

`POST /decisions/approve` requires the same fields plus `executionMode`.
The DTO accepts `shadow`, `canary`, or `controlled`, but only `shadow` is
implemented. The gateway obtains twin, forecast, and simulation context,
then calls the safety service. Caller-provided predictions are not treated
as authoritative for approval. Missing calibrated confidence or fidelity
causes the safety path to reject non-NOOP decisions. Approved shadow decisions
are published with `dry_run: true`; the Go controller validates and audits
them without changing Kubernetes.

The gateway maps public action aliases `serviceId` → `service`, `cpuDelta` →
`cpu_delta`, and `memoryDelta` → `memory_delta_mb` before simulation and safety.
The action object otherwise follows the simulation/controller contract:
`type`, optional `service`, `source`, `destination`, `replicas`, `cpu_delta`,
and `memory_delta_mb` as applicable. Safety's policy endpoint currently
advertises `NOOP`, `MIGRATE`, `PLACE`, and `SCALE`; its approval endpoint
rejects `RESOURCE_ADJUST` because the Go controller does not support it.

## Internal HTTP APIs

### Experiment service (default port 3001)

`GET /health` is public. `POST /experiments`, `GET /experiments`,
`GET /experiments/:id`, `PATCH /experiments/:id`, and
`DELETE /experiments/:id` implement the experiment contract above and require
the service token.

### Infrastructure controller (default port 8081)

| Method and path | Purpose |
| --- | --- |
| `GET /healthz`, `GET /readyz` | Health and readiness. |
| `GET /metrics` | Prometheus text metrics. |
| `GET /infrastructure/nodes`, `GET /infrastructure/pods` | Read-only Kubernetes discovery; 503 if unavailable, 502 on Kubernetes error. |
| `GET /actions`, `GET /actions/:id` | In-process audit records; unknown ID returns 404. |
| `POST /actions/validate` | Validate a `DecisionRequest`; returns `approved` and `reasons`. |
| `POST /actions/execute` | Validate and audit a decision; rejected requests return 422, duplicate IDs 409, and unavailable live actuation 503. |

`DecisionRequest` contains `decision_id`, `policy_version`, `action`,
`predicted`, `dt_fidelity`, `destination_free_cpu`, `destination_healthy`,
`source_healthy`, and optional `dry_run`. Predicted fields include CPU,
latency, SLO violation probability, and prediction confidence. Audit records
are bounded to 10,000 entries. The local Compose deployment sets
`DT_RAM_AUDIT_PATH` on a persistent volume so decision IDs, policy versions,
inputs and verdicts survive controller restarts. Without that variable the
standalone default remains process-local.

### Twin manager (default port 8080)

| Method and path | Purpose |
| --- | --- |
| `GET /healthz`, `GET /readyz`, `GET /metrics` | Health, readiness, and Prometheus metrics. |
| `GET /twin/state` | All node and workload states. |
| `GET /twin/state/:node_id` | One node; missing node returns 404. |
| `POST /twin/update` | Flat telemetry ingest; malformed input returns 400 and invalid state returns 422. |
| `GET /twin/fidelity` | Per-node fidelity, autonomy level, stale flag, and evaluation time. |

`POST /twin/update` requires `node_id` and accepts `cpu`, `memory`,
`network_in`, `network_out`, `cpu_total`, `memory_total_mb`, `health`, and
`timestamp`. Node state includes capacity/usage, network conditions, health,
timestamp, `stale`, and `fidelity`. The flat HTTP body differs from the
nested telemetry event described below. Independent fidelity scoring is not
yet wired into normal ingestion; newly ingested nodes have fidelity zero.

### Prediction service (default port 5000)

`GET /healthz` checks liveness. `GET /readyz` returns 503 without fresh
telemetry. `GET /models` lists registered models. `GET /predictions` accepts
optional `node_id` and `metric` query parameters. Supported metrics are
`cpu`, `memory`, `network_in`, and `network_out`; unsupported metrics return
422. If no usable forecast exists, the endpoint returns 503. Otherwise it
returns the forecast records described under the gateway API, plus errors
for individual unavailable nodes or metrics.

### Simulation service (default port 5002)

`GET /healthz` and `GET /readyz` expose health. `POST /simulate` accepts
`nodes` (array), `candidates` (array), and optional `service_cpu`,
`service_mem_mb`, `predicted`, and `dt_fidelity`. Its `results` array reports
action type, predicted CPU/memory/latency, SLO violation probability,
migration cost and duration, feasibility, notes, confidence, and fidelity.
Each node must supply either utilization `cpu`/`memory` or paired raw
`cpu_used`/`cpu_total` and `memory_used_mb`/`memory_total_mb`. Missing
measurements, including network-in and network-out, are rejected with 422. A missing, stale, or future timestamp
marks state stale, so placement is infeasible. Migration requires a known
source and positive bandwidth. Optional `predicted.forecasts` entries with
`node_id`, `metric` (`cpu` or `memory`), `value`, `horizon_seconds`,
`timestamp`, and `source` are applied only when their node, requested horizon
(default five seconds), and five-second freshness match. The response lists
`applied_forecasts` with provenance. The default no-forecast path remains
unchanged.
Simulation proposes outcomes; it does not actuate.

### Safety service (default port 5003)

`GET /healthz` and `GET /readyz` expose health. `GET /policies` returns
thresholds, supported actions, `execution_modes: ["shadow"]`, and
`physical_actuation: false`.

`POST /validate` accepts `action`, `predicted`, `dt_fidelity`,
`destination_free_cpu`, `destination_healthy`, and `source_healthy`; it
returns `approved` and `reasons`. `POST /decisions/approve` also requires
`decision_id` and `policy_version` and accepts `execution_mode` (default
`shadow`). It returns an approval, published event, and JetStream stream and
sequence acknowledgement. Unsupported mode/action or safety rejection
returns 422; unavailable NATS publication returns 503.

### Telemetry agent (default port 8082)

`GET /healthz`, `GET /readyz`, and `GET /metrics` expose health, readiness,
and Prometheus metrics. `GET /collect` samples node telemetry and publishes
when configured; collection failure returns 500 and publication failure 502.

## NATS JetStream events

The subject list in `infrastructure/networking/nats-subjects.yaml` is a
reference contract, not stream provisioning configuration.

### `dt.telemetry.node_metric` — implemented

The telemetry agent publishes `NODE_METRIC_UPDATED` with `timestamp`,
`node_id`, and nested `metrics` containing `cpu_total`, `memory_total_mb`,
`cpu`, `memory`, `network_in`, and `network_out`. The twin manager and
prediction collector consume it. `DT_TELEMETRY` retains up to 100,000
messages for 24 hours. Publication and consumption use acknowledgements.

### `dt.decisions.resource` — implemented

The safety service publishes approved `RESOURCE_DECISION` events containing
`decision_id`, `policy_version`, `action`, `predicted`, `dt_fidelity`,
destination capacity/health, source health, `dry_run: true`, safety verdict,
and timestamp. The Go controller consumes and audits them. `DT_DECISIONS`
retains up to 10,000 messages for one hour.

### Planned or proposed events

Twin state update and decision result/audit subjects in the reference file
are not published by this checkout. Prediction publisher code proposes a
`NODE_FORECAST_UPDATED` event on `dt.predictions.node_forecast`, but that
subject is not provisioned as an implemented stream contract.

## Implementation references

- Public route and DTO definitions: `services/api-gateway/src/`.
- Experiment persistence: `services/experiment-service/src/experiments/`.
- Go handlers and schemas: `services/{telemetry-agent,twin-manager,infrastructure-controller}/internal/`.
- Python APIs: `services/prediction-service/prediction_app/service.py`,
  `services/simulation-service/app/main.py`, and
  `services/safety-service/safety_app/main.py`.
- Event subjects: `infrastructure/networking/nats-subjects.yaml`.
