# DT-RAM

Digital Twin Reinforcement-Learning Assisted Resource Management for edge–cloud infrastructure.

The control path keeps prediction and RL separate from Kubernetes actuation:

```text
Telemetry → Digital Twin → Prediction → RL recommendation
          → Counterfactual simulation → Safety gate
          → Go infrastructure controller → Kubernetes
```

## Agent 1 services

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
