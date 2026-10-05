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

Controller ships with `CONTROLLER_DRY_RUN=true` so no cluster mutation
happens until safety-gated execution is explicitly enabled.

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
