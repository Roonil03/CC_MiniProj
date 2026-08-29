# DT-RAM: Digital-Twin-Assisted Resource Management for Edge Computing

[![Project Status: Active Development](https://img.shields.io/badge/Project%20Status-Active%20Development-blue.svg)](#)
[![Architecture: Microservices](https://img.shields.io/badge/Architecture-Cloud--Edge%20Microservices-green.svg)](#)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Go: 1.21+](https://img.shields.io/badge/Go-1.21%2B-cyan.svg)](https://golang.org/)
[![Node: 18+](https://img.shields.io/badge/Node.js-18%2B-brightgreen.svg)](https://nodejs.org/)

DT-RAM is a production-grade research platform that pairs a real-time synchronized **Digital Twin** of an edge–cloud computing continuum with predictive machine learning and reinforcement learning (PPO) for proactive, safety-gated workload scheduling and microservice migration.

---

## 📌 Architecture Overview

```text
Physical Edge/Cloud Infrastructure (Kubernetes/K3s)
              │
              ▼
    Telemetry Collection (Go)
              │
              ▼
    Digital Twin State (Python / Go)
              │
        ┌─────┴─────┐
        ▼           ▼
  State Forecast   Current State
        │           │
        └─────┬─────┘
              │
              ▼
    Counterfactual Simulator (Python)
              │
              ▼
    RL Decision Engine (Python / PPO)
              │
              ▼
    Safety / Policy Gate
              │
              ▼
    Physical Actuator & Controller (Go)
              │
              ▼
    Updated Infrastructure State (Closed-Loop Feedback)
```

---

## 📂 Repository Structure

```text
dt-ram/
├── .github/              # GitHub Actions workflows & PR/Issue templates
├── datasets/             # Trace datasets (raw, processed)
├── docs/                 # System architecture, research gap, experiment documentation
├── experiments/          # Evaluation configs, baseline implementations, run logs
├── infrastructure/       # Docker Compose, Kubernetes/K3s manifests, Helm charts, Prometheus
├── services/             # Core microservices
│   ├── api-gateway/              # TypeScript / NestJS API Gateway
│   ├── experiment-service/       # TypeScript / Node.js Experiment Manager
│   ├── infrastructure-controller/# Go Kubernetes Controller & Actuator
│   ├── telemetry-agent/          # Go Node/Pod Telemetry Collector
│   ├── twin-manager/             # Go / Python Digital Twin State Manager
│   ├── prediction-service/       # Python Forecasting (LSTM, GRU, Temporal Baselines)
│   ├── rl-service/               # Python Gymnasium + Stable-Baselines3 RL Engine
│   ├── simulation-service/       # Python Counterfactual Scenario Simulator
│   └── safety-service/           # Safety constraint validation engine
├── workloads/            # Edge test workloads (gateway, processor, analytics, worker)
├── scripts/              # Automation and deployment scripts
├── CONTRIBUTING.md       # Contribution, branching, and development guidelines
├── CODEOWNERS            # Component ownership mapping
├── SECURITY.md           # Security policy and disclosure
├── .gitignore            # Git exclusion rules (venv, node_modules, weights, secrets)
└── .env.example          # Environment variable template
```

---

## 🚀 Quickstart & Setup Guide

### 1. Python Microservices (`prediction-service`, `rl-service`, `simulation-service`, `safety-service`)
> **Important:** Always activate a virtual environment and install dependencies via `pip3`.

```bash
# Navigate to the target service directory
cd services/prediction-service

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate       # On Windows: .\venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
pip3 install --upgrade pip
pip3 install -r requirements.txt
```

### 2. Node.js / TypeScript Microservices (`api-gateway`, `experiment-service`)
```bash
cd services/api-gateway
npm install
npm run dev
```

### 3. Go Microservices (`infrastructure-controller`, `telemetry-agent`, `twin-manager`)
```bash
cd services/infrastructure-controller
go mod tidy
go build ./cmd/...
```

---

## 👥 Team & Component Allocation

Refer to [`CODEOWNERS`](CODEOWNERS) and [`Design.md`](Design.md) for full breakdown:
- **Member 1**: API Gateway, Experiment Service & Dashboard Backend (Node.js/TypeScript)
- **Member 2**: Infrastructure Controller, Telemetry Collector & Kubernetes Actuation (Go)
- **Member 3**: Time-Series Forecasting & Workload Prediction (Python/PyTorch)
- **Member 4**: Digital Twin State, Counterfactual Simulation & RL Policy (Python/Gymnasium/SB3)

---

## 📖 Documentation
- Comprehensive system design: [`Design.md`](Design.md)
- Contributing rules and workflow: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security reporting: [`SECURITY.md`](SECURITY.md)
