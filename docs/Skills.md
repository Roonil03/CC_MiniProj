# Skills.md

Project-specific skill catalogue for AI coding agents working on DT-RAM.

These are workflow definitions, not mandatory personas. An agent should select the smallest applicable skill set for the task.

## 1. Repository Exploration

**Use when:** starting work in an unfamiliar area.

### Goal
Understand the existing implementation before changing it.

### Procedure
1. Locate the relevant service/module.
2. Read its README/documentation, entry points and configuration.
3. Inspect nearby tests.
4. Trace its public inputs and outputs.
5. Check applicable `AGENTS.md` files.
6. Identify dependencies on other services.
7. Summarize findings before implementation.

### Do not
- scan or rewrite the entire repository unnecessarily;
- infer an API from the design document if the implementation already defines one.

---

## 2. Service Implementation

**Use when:** adding or modifying a microservice component.

### Goal
Implement one bounded service responsibility while preserving service boundaries.

### Procedure
1. Identify the service owner and interface.
2. Follow the service's existing language/framework conventions.
3. Keep business logic inside the appropriate service.
4. Add focused tests.
5. Verify build/test behaviour.
6. Document externally visible interface changes.

### Boundary
Do not move logic between Node.js, Go and Python merely for convenience.

---

## 3. Digital Twin

**Use when:** modifying DT state, synchronization, fidelity or virtual infrastructure modelling.

### Goal
Maintain a consistent virtual representation of the physical edge–cloud system.

### Key concepts
- node state;
- workload/service state;
- resource usage;
- network conditions;
- timestamps/freshness;
- synchronization;
- fidelity;
- consistency.

### Rules
- State must be timestamped.
- Stale state must be detectable.
- Physical and virtual state should be distinguishable.
- Do not silently invent telemetry values.
- Changes to the state schema must remain compatible with consumers.

---

## 4. Simulation / Counterfactual Evaluation

**Use when:** implementing the Digital Twin simulator or evaluating candidate actions.

### Goal
Answer:

> "What is likely to happen if this action is taken?"

### Candidate actions may include
- no-op;
- placement change;
- migration;
- scaling;
- resource adjustment.

### Simulation should consider
- CPU;
- memory;
- network;
- latency;
- workload/request rate;
- queueing;
- SLO impact;
- migration cost;
- destination capacity;
- failures/degradation where relevant.

### Rule
A simulated action is a recommendation/evaluation result. It is not permission to modify Kubernetes.

---

## 5. Reinforcement Learning

**Use when:** implementing the RL environment, reward, policy or training pipeline.

### Goal
Learn resource-management decisions in a reproducible simulated environment.

### Default direction
Start with **PPO** and a single-agent baseline.

### Required concepts
- state;
- action space;
- reward;
- constraints;
- episode/reset behaviour;
- deterministic configuration where possible;
- evaluation metrics.

### Good progression
```text
Heuristic
→ RL baseline
→ DT + RL
→ Prediction + DT + RL
→ Counterfactual DT-RL
→ Safety-constrained system
```

### Do not
- begin with MARL without justification;
- train against uncontrolled production infrastructure;
- allow the RL process to call Kubernetes directly;
- hide unsafe actions by manipulating evaluation code.

---

## 6. Prediction / Forecasting

**Use when:** modifying workload/resource prediction.

### Goal
Predict future infrastructure state in a way useful to resource management.

### Baselines
- persistence;
- ARIMA/ETS;
- LSTM/GRU;
- lightweight temporal/Transformer model.

### Evaluate
- MAE;
- RMSE;
- appropriate MAPE/R²;
- inference latency;
- model size;
- CPU/memory cost.

### Important
The best RMSE model is not automatically the best operational model.

Avoid random train/test splits for time-series data. Preserve temporal ordering.

---

## 7. Safety & Policy

**Use when:** changing action validation, constraints, autonomy or physical actuation.

### Goal
Prevent an ML/RL recommendation from becoming an unsafe infrastructure action.

### Pipeline
```text
Candidate action
→ DT evaluation
→ constraint checks
→ safety approval
→ Go controller
→ Kubernetes
```

### Reject or reduce autonomy when applicable
- DT state is stale;
- prediction confidence is too low;
- destination lacks capacity;
- node is unhealthy;
- SLO would be violated;
- migration limits are exceeded;
- required safety service is unavailable.

### Principle
Safety must be enforced by explicit checks, not merely by reward shaping.

---

## 8. Kubernetes / Infrastructure

**Use when:** changing physical deployment, telemetry, migration or orchestration.

### Goal
Operate Kubernetes through the controlled infrastructure layer.

### Rules
- Go owns physical actuation.
- Python services propose decisions.
- Do not grant RL/ML unrestricted Kubernetes permissions.
- Prefer labels/configuration already established by the repository.
- Avoid destructive cluster operations during development unless explicitly requested.

---

## 9. Experiment Design

**Use when:** adding benchmarks, workloads, ablations or research experiments.

### Goal
Produce results that can be reproduced and compared.

### Record
- Git SHA;
- configuration;
- dataset/version;
- seed;
- model/policy version;
- topology/environment;
- metrics.

### Preferred comparisons
- Kubernetes/default or static heuristic;
- reactive heuristic;
- RL without DT;
- DT + RL;
- DT + prediction + RL;
- full safety-constrained system.

### Workload profiles
- stable;
- periodic;
- bursty;
- failure/adversarial;
- network degradation;
- resource contention.

---

## 10. Testing & Verification

**Use when:** validating any implementation change.

### Procedure
1. Run the smallest relevant test first.
2. Run build/type/lint checks applicable to the changed service.
3. Test changed interfaces.
4. For ML, run a lightweight model/data smoke test.
5. For infrastructure, prefer non-destructive tests.
6. Inspect the final diff.

### Rule
Never report a check as passed unless it actually ran.

---

## 11. Documentation / Research

**Use when:** changing architecture, methodology, experiments or research claims.

### Goal
Keep implementation and research documentation aligned.

### Update when relevant
- architecture;
- API/interface contracts;
- DT model;
- RL formulation;
- prediction methodology;
- experiment configuration;
- results;
- limitations.

Do not claim novelty merely because the project combines Digital Twins and RL. The intended contribution is the integrated predictive, counterfactual, safety-constrained closed loop.

---

## 12. Git / PR Hygiene

**Use when:** preparing changes for review.

### Checklist
- change is scoped;
- tests/checks were run;
- no secrets or generated artifacts were added;
- commit explains what and why;
- PR describes problem, solution, testing, research relevance and limitations.

### Avoid
```text
changes
update
stuff
final
final2
working
```

Use meaningful commit types such as:

```text
feat
fix
refactor
test
docs
experiment
research
chore
perf
ci
```

---

## Skill Selection Shortcut

```text
API/backend              → Service Implementation
Go/Kubernetes             → Kubernetes / Infrastructure
Digital Twin              → Digital Twin
Simulator                 → Simulation / Counterfactual
PPO/RL                    → Reinforcement Learning
Forecasting               → Prediction / Forecasting
Safety                    → Safety & Policy
Benchmarks/ablations      → Experiment Design
Tests/CI                  → Testing & Verification
Paper/design docs         → Documentation / Research
Git/PR                    → Git / PR Hygiene
Unknown area              → Repository Exploration first
```
