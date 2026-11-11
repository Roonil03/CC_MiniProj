# DT-RAM

**Digital Twin Reinforcement-Learning Assisted Resource Management** is a research project for managing resources across edge–cloud infrastructure. It collects Kubernetes telemetry, maintains a Digital Twin, forecasts resource demand, and evaluates resource decisions in simulation before a safety gate considers them.

```text
Telemetry → Digital Twin → Prediction → RL recommendation
          → Counterfactual simulation → Safety gate
          → Go controller → Kubernetes
```

The system uses a Node.js API gateway and experiment registry, Go telemetry and infrastructure services, and Python prediction, simulation, safety, and PPO components. NATS JetStream carries events, PostgreSQL stores experiments, and Redis can persist twin state. **Physical actuation is currently disabled:** approved decisions run in shadow mode and are audited without changing Kubernetes.

## Explore the project

- [Docker and k3d terminal demo](docs/demo.md) — inspect live node health and metrics, then evaluate illustrative shadow-only candidates
- [API and event reference](docs/api.md)
- [Local deployment and infrastructure guide](infrastructure/README.md)
- [Experiment protocol](docs/experiments.md)

For local setup, copy `.env.example` to `.env`, set `DT_RAM_API_KEY`, `DT_RAM_SERVICE_TOKEN`, and `POSTGRES_PASSWORD`, then follow the infrastructure guide. The gateway serves its interactive API docs at `/docs` on port `3000` by default.

## Capability status

| Capability | Status | Boundary |
| --- | --- | --- |
| Offline forecasting sweep and plots | Implemented; synthetic trial recorded | No real cluster generalization claim; [trial-01 results](docs/analysis/trial-01-synthetic-forecasting-2026-11-11.md) are generated fixtures |
| Synthetic twin, counterfactual simulation and PPO evaluation | Simulated | Results are not live-cluster evidence |
| Safety decision publication and Go controller audit | Shadow-only | Physical Kubernetes actuation is disabled |
| Autonomous production migration | Planned | No deployment claim |

Windows users can run the offline, project-local [model runner](scripts/run_dt_models.ps1).
See [the experiment guide](docs/experiments.md) for its inputs, archive and limits.
