# DT-RAM

Digital Twin Reinforcement-Learning Assisted Resource Management for edge–cloud infrastructure.

The control path keeps prediction and RL separate from Kubernetes actuation:

```text
Telemetry → Digital Twin → Prediction → RL recommendation
          → Counterfactual simulation → Safety gate
          → Go infrastructure controller → Kubernetes
```

## Member 1 services

- `services/api-gateway`: authenticated NestJS API, OpenAPI documentation, dashboard aggregation, state/model APIs, experiment forwarding, and safe decision forwarding.
- `services/experiment-service`: PostgreSQL-backed experiment CRUD with mandatory reproducibility metadata.

Copy `.env.example` to `.env`, replace both authentication placeholders, and configure PostgreSQL. Install and run each Node service from its own directory:

```text
npm install
npm run build
npm test
npm start
```

The API gateway listens on port `3000` and the experiment service on `3001` by default. Their interactive OpenAPI documents are available at `/docs`; health checks are available at `/health` without authentication.

See [the API guide](docs/api.md) and [the system architecture](docs/architecture.md) for details.

## Member 2 services and infrastructure

- `services/telemetry-agent`: Go/Gin host CPU, memory and network collection, measured node capacity, acknowledged NATS JetStream publishing, and Prometheus metrics. Kubernetes deployment runs one agent per node with a DaemonSet.
- `services/twin-manager`: telemetry synchronization, timestamp ordering and input validation, read-time freshness checks, twin state/fidelity APIs, retained telemetry replay, and optional Redis write-through persistence with restart recovery.
- `services/infrastructure-controller`: shared HTTP/NATS decision validation and auditing, duplicate decision-ID rejection, confidence/fidelity and migration-limit checks, read-only Kubernetes node/pod discovery, and a SCALE executor tested with fake Kubernetes.
- `infrastructure`: Docker Compose, Kubernetes services and least-privilege RBAC, persistent NATS/Redis deployments, k3d topology, Prometheus scrape configuration, TimescaleDB bootstrap DDL, and cluster-free manifest regression tests.

The Go services listen on ports `8082` (telemetry), `8080` (twin), and `8081` (controller). Each exposes `/healthz` and `/metrics`. Supported sampling, freshness and safety tunables load from `configs/config.yaml`; environment variables configure service identity and transport. Set `REDIS_ADDR` to enable persistent twin storage.

Run these checks from each Go service directory:

```text
go build ./...
go vet ./...
go test ./...
```

From the repository root, validate or start the local infrastructure stack:

```text
docker compose -f infrastructure/docker/docker-compose.yml config
docker compose -f infrastructure/docker/docker-compose.yml up --build
```

Live controller actuation remains disabled until authoritative twin, counterfactual and safety-service integration is available. Migration, placement/rollback and `RESOURCE_ADJUST` are not implemented. Audit records remain process-local; TimescaleDB has bootstrap DDL but no historical event sink. Docker image builds and real-cluster deployment still require validation.

See [the infrastructure guide](infrastructure/README.md) for deployment and configuration details, and [the Member 2 work log](member2.txt) for completed tasks, verification evidence and the integration handoff.
