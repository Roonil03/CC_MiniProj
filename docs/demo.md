# Docker and k3d terminal demo

The demo runs a read-only, shadow-only DT-RAM walkthrough against a local k3d Kubernetes cluster. It displays node state, forecasts utilization in live mode, and evaluates illustrative candidates through the simulator and safety gate. It never changes Kubernetes resources. The launcher creates the `dt-ram` cluster from `infrastructure/k3s/k3d.yaml` when absent and reuses it when present; the cluster remains running after the demo exits.

## Requirements

- Docker with a running Docker daemon
- k3d
- A working network connection to build the image and download kubectl on the first run

The launchers build the image from the repository root, mount a temporary kubeconfig read-only into the container, and stream output to the terminal. They run the container with Docker's init process and allocate an interactive terminal only for an interactive session (never for JSON output or piped output). Python and kubectl do not need to be installed on the host. The container image includes NumPy, statsmodels, and the prediction service's `prediction_app.models` module for the live forecasts.

## Run the demo

From the repository root:

```bash
bash scripts/demo.sh
```

```powershell
./scripts/demo.ps1
```

By default, the launchers start the continuous live feed. Press Ctrl+C to stop it; this does not stop the cluster. Each tick reads Kubernetes nodes and `metrics.k8s.io`, updates the in-process twin, forecasts CPU and memory utilization, and evaluates illustrative counterfactuals. Kubernetes API or metrics errors are retried on later ticks; ten consecutive failed ticks stop the feed.

For one snapshot, JSON output, or the built-in synthetic fixture:

```bash
bash scripts/demo.sh --once
bash scripts/demo.sh --json
bash scripts/demo.sh --synthetic --seed 42
```

```powershell
./scripts/demo.ps1 --once
./scripts/demo.ps1 --json
./scripts/demo.ps1 --synthetic --seed 42
```

The launcher always forwards `--live`; the Python CLI gives `--once`, `--json`, and `--synthetic` precedence over it. `--once` prints one Kubernetes snapshot and exits. `--json` prints one snapshot in machine-readable form, with launcher setup/status messages sent to stderr. `--synthetic` uses deterministic illustrative node data (the seed controls small fixture variations). The launcher still checks or creates the k3d cluster and builds the image before starting synthetic mode; running `scripts/demo.py --synthetic` directly does not require Kubernetes. Other options include `--no-color`, `--interval` (minimum one second), `--ticks` (zero runs until interrupted), and `--history` (13–600 retained samples per node metric).

## Reading the output

Live CPU and memory are node usage samples from Kubernetes Metrics API; health is read from node conditions. They describe the local k3d testbed, not physical edge hardware. The listed workload candidates are illustrative. P95 latency, SLO violation probability, and migration cost are simulator estimates, not measurements of running workloads.

The live twin has no independent, scope-matched reference stream, so its fidelity is zero. Forecast confidence is a score derived from rolling mean absolute error between forecasts and later observations (`clamp(1 - MAE, 0, 1)`); it is zero until a forecast has been realized. It is not a calibrated probability of correctness. The safety gate uses the measured score and fails closed for non-no-op actions while twin fidelity is zero. In one-shot Kubernetes and synthetic modes there is no measured forecast history, so confidence is zero and non-no-op actions are denied. Synthetic fidelity is compared with independent synthetic reference samples; neither that score nor the simulated candidates validate real infrastructure.

All output and verdicts are informational: candidates are never sent to the Go controller and no actuation occurs. One-shot mode waits for node metrics samples; live mode retries failed ticks. If the Kubernetes API is unreachable or metrics do not become available, check that the cluster is ready and its Metrics API is serving samples.
