# Infrastructure (Member-2)

Containerized local stack and Kubernetes manifests for DT-RAM.

## Local stack

```bash
docker compose -f infrastructure/docker/docker-compose.yml config
docker compose -f infrastructure/docker/docker-compose.yml up --build
```

Services and ports (see `.env.example`): telemetry-agent `8082`,
twin-manager `8080`, infrastructure-controller `8081`, NATS `4222/8222`,
Redis `6379`, Postgres/Timescale `5432`, Prometheus `9090`.

Controller ships with `CONTROLLER_DRY_RUN=true`. Live requests are rejected
with 503 even when this flag is false: authoritative twin freshness,
counterfactual evaluation and the Member 4 safety-service contract are pending.
Caller-supplied fidelity and health fields are sufficient only for dry-run
validation. Fidelity must exceed 0.95 and prediction confidence must be at
least 0.80; missing confidence is rejected. RESOURCE_ADJUST is unsupported.

HTTP and NATS decisions share the same audit pipeline. `decision_id` is required
for execution requests; reused IDs return 409 over HTTP. Audit is in memory.
Twin state uses memory by default; set REDIS_ADDR for write-through persistence
and startup restoration. Configured Redis failures reject updates; restoration
failures stop startup. Deploy one twin-manager writer: hot reads are local.
Postgres/Timescale currently provides DDL only, without an event sink.

The controller exposes read-only `GET /infrastructure/nodes` (Kubernetes
NodeList) and `GET /infrastructure/pods` (PodList restricted to K8S_NAMESPACE).
Discovery works in dry-run mode. Missing cluster credentials return 503;
upstream Kubernetes errors return 502. Node status, allocatable resources,
pod placement and resource requests are available in these native objects.

The low-level SCALE executor is tested with fake Kubernetes. MIGRATE and PLACE
return errors: the previous Deployment annotation did not actually move pods.
Rollout verification, reversible placement, capacity checks and authenticated
live actuation remain dependent on the integrated control loop.

## Kubernetes (k3d)

```bash
k3d cluster create --config infrastructure/k3s/k3d.yaml
kubectl apply -f infrastructure/kubernetes/00-namespace-rbac.yaml
kubectl apply -f infrastructure/kubernetes/10-go-services.yaml
```

RBAC: only the `dt-ram-controller` ServiceAccount may write
deployments/scales in `dt-ram`. ML/RL services receive no write bindings
(Design.md Sections 65-66).

## Subjects

See `infrastructure/networking/nats-subjects.yaml` for the NATS subject
table. Timescale bootstrap: `infrastructure/monitoring/initdb/01-schema.sql`.

Telemetry uses acknowledged JetStream publication. DT_TELEMETRY retains up to
100,000 messages for 24 hours; twin-manager uses an ephemeral acknowledged
consumer to rebuild its in-memory state from retained telemetry after restart.
This is bounded replay, not a durable database. Older or duplicate node samples
are rejected. DT_DECISIONS retains up to 10,000 messages for one hour and uses
the durable infrastructure-controller consumer. Invalid events are terminated;
handled decisions (including rejections) are acknowledged.

An agent with TELEMETRY_PUBLISH_ENABLED=true exits when JetStream cannot be
initialized. Twin/controller may start HTTP-only when NATS is absent at startup;
restart them after NATS returns. Stream/subscription setup failures are logged.

All three Go services expose `/metrics`. Twin metrics report node/stale counts;
controller metrics report current audit/rejection counts. Telemetry gauges
update during periodic sampling as well as GET /collect.

To run the optional JetStream test against an isolated local server, set
NATS_TEST_URL and run `go test ./internal/publisher` in telemetry-agent.
