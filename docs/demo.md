# Docker and k3d terminal demo

The demo runs in a Docker container and reads a live k3d Kubernetes cluster. It prints node status and resource metrics, evaluates illustrative candidates against the Digital Twin and safety gate, and remains **shadow-only**: it does not create, change, or delete Kubernetes resources. The launcher creates the documented `dt-ram` cluster when it is absent and reuses it when present. It leaves the cluster running after the demo exits.

## Requirements

- Docker with a running Docker daemon
- k3d
- A working network connection the first time, to download the demo image dependencies

The cluster must be reachable and expose the Kubernetes Metrics API (`metrics.k8s.io`) with a sample for every node. The launchers build the image from the repository root, pass a temporary kubeconfig into the container, and stream its output to the terminal. You do not need to install Python or kubectl on the host.

## Run the demo

From the repository root, run one of:

```bash
bash scripts/demo.sh
```

```powershell
./scripts/demo.ps1
```

The first run creates the `dt-ram` k3d cluster from `infrastructure/k3s/k3d.yaml` if needed. Later runs reuse it. The container uses kubectl to read node objects and node metrics. It does not read workload metrics or send infrastructure changes.

To print machine-readable output or disable terminal colors, pass the demo options through the launcher:

```bash
bash scripts/demo.sh --json
bash scripts/demo.sh --no-color
```

```powershell
./scripts/demo.ps1 --json
./scripts/demo.ps1 --no-color
```

The original synthetic fixture remains available with `--synthetic`; it does not use live cluster data. The seed controls its deterministic variation:

```bash
bash scripts/demo.sh --synthetic --seed 42
```

## Reading the output

Live node CPU and memory values come from Kubernetes Metrics API samples; node health comes from Kubernetes node conditions. These values are observations of the local k3d testbed and are not measurements from physical edge hardware. The scenario candidates are illustrative and do not describe the workloads actually running in the cluster. P95 latency, SLO violation probability, and migration overhead are simulator estimates, not production measurements.

The Digital Twin has no independent, scope-matched reference measurement in this demo, so its fidelity remains zero. It also has no live prediction model, so prediction confidence remains zero. The safety gate therefore fails closed for non-no-op candidates. An approved no-op or any printed verdict is informational only. No candidate is sent to the Go controller, and no actuation is performed.

The demo fails with an error if the Kubernetes API is unreachable or if node metrics are unavailable for any node. Ensure the cluster is ready and its metrics-server has populated samples, then rerun the launcher.
