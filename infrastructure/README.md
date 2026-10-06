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
for execution requests; reused IDs return 409 over HTTP. Audit and twin state
are in memory and do not survive restarts. Redis/Postgres sinks are pending.

The controller exposes read-only `GET /infrastructure/nodes` (Kubernetes
NodeList) and `GET /infrastructure/pods` (PodList restricted to K8S_NAMESPACE).
Discovery works in dry-run mode. Missing cluster credentials return 503;
upstream Kubernetes errors return 502. Node status, allocatable resources,
pod placement and resource requests are available in these native objects.

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
