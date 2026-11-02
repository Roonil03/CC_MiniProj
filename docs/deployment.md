# Deployment & Cluster Setup Guide

## Local integration stack

Validate the complete service graph without starting workloads:

```text
docker compose -f infrastructure/docker/docker-compose.yml config
docker compose -f infrastructure/docker/docker-compose.yml build
```

Copy `.env.example` to `.env` and replace both authentication placeholders.
The default stack includes the Node gateway/experiment services, Go
telemetry/twin/controller services, prediction API/collector, simulation, and
safety. The RL CLI is opt-in through the `experiments` Compose profile and
does not expose a Jupyter server.

The approval path is shadow-only. Safety publishes an acknowledged
`dt.decisions.resource` event with `dry_run=true`; the Go controller audits it
without changing Kubernetes. Do not enable live actuation until rollback,
placement verification, and production model/policy validation exist.

## Kubernetes and K3s

Kubernetes and K3s topology setup, Prometheus, and Grafana deployment are
covered by the manifests under `infrastructure/kubernetes/` and the topology
configuration in `infrastructure/k3s/`.
