# AGENTS.md

## Purpose

This repository implements **DT-RAM (Digital Twin Reinforcement-Learning Assisted Resource Management)**: a Digital-Twin-assisted resource-management system for edge–cloud infrastructure.

The system observes Kubernetes infrastructure, synchronizes a Digital Twin, predicts future state, evaluates candidate resource-allocation/migration decisions, applies safety constraints, and only then performs approved actions through a controlled infrastructure layer.

## Core Architecture

Keep the following boundary intact:

```text
Telemetry / Physical State
        ↓
Digital Twin State
        ↓
Prediction (Python / ML)
        ↓
Decision / RL (Python)
        ↓
Counterfactual Simulation
        ↓
Safety / Policy Gate
        ↓
Infrastructure Controller (Go)
        ↓
Kubernetes
        ↓
Observed Outcome
        ↺
```

**Never allow the Python RL/ML layer to directly control Kubernetes.**

The intended separation is:

- **Node.js / TypeScript:** API gateway, experiment-facing APIs and application-facing orchestration.
- **Go:** infrastructure control, telemetry, Kubernetes integration, migration/actuation.
- **Python:** forecasting, Digital Twin simulation, RL, policy evaluation and experiments.
- **Kubernetes:** physical infrastructure control plane.
- **PostgreSQL / TimescaleDB:** persistent and time-series state.
- **NATS JetStream:** asynchronous event transport unless the project explicitly changes this decision.
- **Prometheus / Grafana:** metrics and visualization.

## Before Making Changes

1. Read the relevant files before editing them.
2. Check for a more specific `AGENTS.md` in the directory being changed.
3. Read the relevant service documentation and tests.
4. Identify the service boundary and its inputs/outputs.
5. Make the smallest change that completes the requested task.
6. Do not invent APIs, configuration keys, environment variables, schemas, commands, test results, or infrastructure that has not been verified.
7. If the repository's existing implementation differs from the design document, inspect the implementation and preserve working local conventions unless the task explicitly asks for architectural changes.

## Agent Workflow

For every non-trivial task:

```text
Understand → Plan → Implement → Test → Inspect diff → Report
```

Before implementation, briefly state:
- what will change;
- which files/services are involved;
- how the change will be verified.

After implementation:
- run the narrowest relevant tests first;
- run broader checks when practical;
- inspect the final diff;
- report failures honestly.

Do not claim a test passed unless it was actually run.

## Scope Control

Do not:
- rewrite unrelated code;
- perform broad refactors while implementing a small feature;
- replace working components merely because another technology is preferred;
- add unnecessary dependencies;
- introduce an LLM into the resource-management loop;
- start with multi-agent RL when a single-agent PPO baseline is sufficient;
- give the RL service unrestricted Kubernetes credentials.

The project's initial RL direction is **PPO**, with more advanced algorithms considered only after a reliable baseline exists.

## Safety-Critical Boundary

Candidate decisions must follow:

```text
RL recommendation
      ↓
Digital Twin / counterfactual evaluation
      ↓
Constraint + safety validation
      ↓
Go infrastructure controller
      ↓
Kubernetes
```

Safety checks should consider, where applicable:

- CPU and memory capacity;
- SLO/latency constraints;
- destination capacity;
- node health;
- network availability;
- Digital Twin freshness/fidelity;
- prediction confidence;
- migration limits/cooldowns;
- rollback or fallback behaviour.

If the Digital Twin is stale, prediction confidence is inadequate, or the safety layer is unavailable, prefer a safe fallback rather than autonomous actuation.

## Digital Twin Rules

The Digital Twin is more than a database. It represents:

- synchronized infrastructure state;
- workloads/services;
- resource usage;
- network conditions;
- workload dynamics;
- migration state;
- prediction interfaces;
- simulation state;
- fidelity/consistency information.

Counterfactual simulation should evaluate alternatives such as:

- no-op;
- resource adjustment;
- service migration;
- scaling;
- alternative placement.

The simulator should account for resource, workload, network and migration dynamics rather than treating migration as free.

## ML / RL Rules

Prediction and decision are separate concerns.

Prediction models may include:
- persistence baseline;
- ARIMA/ETS;
- LSTM/GRU;
- lightweight temporal/Transformer models.

RL should initially use:
- a clearly defined state;
- explicit action space;
- reproducible reward;
- PPO baseline;
- deterministic experiment configuration where possible.

Do not train RL primarily against unrestricted physical infrastructure. Simulation should be the main training environment, with physical deployment used for controlled validation.

## Experiments

Experiments must be reproducible.

Record, where applicable:

- Git commit;
- dataset/version;
- configuration;
- random seed;
- model/policy version;
- environment/topology;
- metrics;
- results.

Prefer the project's progression:

```text
Static heuristic
→ Reactive heuristic
→ Prediction
→ RL without DT
→ DT + RL
→ DT + Prediction + RL
→ Counterfactual DT-RL
→ Full system + Safety
```

Do not manufacture meaningless experiment runs or commits.

## Git

Use the repository's established branch strategy:

```text
main
develop
feature/*
experiment/*
research/*
```

Do not commit experimental work directly to `main`.

Prefer meaningful conventional commit messages such as:

```text
feat(rl): add PPO migration environment
feat(twin): add synchronized node state model
fix(twin): reject stale state updates
experiment: add burst workload benchmark
docs: document counterfactual decision flow
```

Every meaningful feature should be reviewed through a pull request.

## Service Ownership

The design divides the system broadly as:

```text
Member 1 → Node.js / TypeScript
Member 2 → Go / Infrastructure
Member 3 → ML / Prediction
Member 4 → ML / RL + Digital Twin
```

CODEOWNERS is authoritative for actual repository ownership.

Do not modify another member's component unnecessarily. Coordinate through stable interfaces, schemas and events.

## Verification

Verification should be proportional to the change.

At minimum:
- changed code should build/import successfully;
- changed behaviour should have a focused test where practical;
- API/schema changes should have contract or validation coverage;
- ML changes should include a smoke test/data validation where applicable;
- infrastructure changes should be tested without requiring destructive operations.

Never weaken tests or remove validation merely to make CI pass.

## Security

Never commit:
- secrets;
- API keys;
- credentials;
- certificates/private keys;
- kubeconfigs;
- model/data artifacts that are explicitly excluded by `.gitignore`.

The RL/ML services must not receive unrestricted Kubernetes permissions.

## Documentation

When changing architecture, interfaces, experiment methodology, or research behaviour, update the relevant documentation.

Keep documentation consistent with the implementation. Do not document functionality that does not exist.

## When Unsure

Prefer:

1. inspect the repository;
2. inspect the relevant design/documentation;
3. inspect tests and interfaces;
4. make the smallest defensible change;
5. ask for clarification only when two materially different interpretations remain.

Do not guess.
