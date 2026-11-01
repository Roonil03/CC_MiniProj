# Member 2 testbed validation and telemetry handoff

This runbook covers the Go/Kubernetes boundary only. It does not enable live
resource decisions, migration, or rollback. Use a new run ID for each capture,
such as `k3d-20261101T120000Z-<git-short-sha>`. Record the actual UTC start and
end times; do not label an idle trace as a workload or fault experiment.

## Preconditions

Run from the repository root. Docker Desktop (or another Docker daemon), k3d,
and kubectl must work before creating a local cluster. An existing K3s cluster
may be used only with an explicitly selected context and a verified namespace.
The documented k3d configuration creates one server and two agent nodes with
cloud, edge-a, and edge-b labels. This is a containerized development testbed,
not evidence from physical edge hardware.

On Windows, keep the generated kubeconfig in an ignored local path such as
`local-dev/run/kubeconfig.yaml` and set `KUBECONFIG` to that path in each
terminal. In the validated run, k3d wrote `host.docker.internal` as the API
server host, which the Windows session could not reach. After checking the
published `6443` port with `docker ps`, changing only this local kubeconfig's
server host to `127.0.0.1` restored access. Do not commit the kubeconfig.
For a new local run, set the path before `k3d cluster create`:

```powershell
New-Item -ItemType Directory -Force local-dev/run | Out-Null
$env:KUBECONFIG = (Join-Path (Get-Location) 'local-dev/run/kubeconfig.yaml')
```

```powershell
docker info
k3d version
kubectl config current-context
git rev-parse HEAD
```

If the daemon or cluster is unavailable, stop at static validation and record
the blocker. Do not manufacture testbed telemetry or use a synthetic fixture as
a research dataset. Do not commit kubeconfigs, credentials, or raw traces.

## Deploy the Go testbed in shadow mode

Create the local cluster only if it does not already exist. Review the current
context before applying manifests. Build and import the three Go images; the
manifests use `IfNotPresent` and do not pull unpublished `latest` tags.

```powershell
k3d cluster create --config infrastructure/k3s/k3d.yaml
docker build -t dt-ram/telemetry-agent:latest services/telemetry-agent
docker build -t dt-ram/twin-manager:latest services/twin-manager
docker build -t dt-ram/infrastructure-controller:latest services/infrastructure-controller
k3d image import -c dt-ram dt-ram/telemetry-agent:latest dt-ram/twin-manager:latest dt-ram/infrastructure-controller:latest
kubectl apply -f infrastructure/kubernetes/00-namespace-rbac.yaml
kubectl apply -f infrastructure/kubernetes/05-nats.yaml
kubectl apply -f infrastructure/kubernetes/06-redis.yaml
kubectl rollout status -n dt-ram statefulset/nats
kubectl rollout status -n dt-ram statefulset/redis
kubectl apply -f infrastructure/kubernetes/10-go-services.yaml
kubectl rollout status -n dt-ram daemonset/telemetry-agent
kubectl rollout status -n dt-ram deployment/twin-manager
kubectl rollout status -n dt-ram deployment/infrastructure-controller
```

Check node labels and pod placement with `kubectl get nodes --show-labels` and
`kubectl get pods -n dt-ram -o wide`. Expect one telemetry pod per schedulable
node and a healthy NATS/Redis/twin/controller. Inspect events and logs for any
failed rollout. Verify the controller deployment still has
`CONTROLLER_DRY_RUN=true`; its public decision processor also rejects live
requests. The controller ServiceAccount may read nodes and only update
deployments/scales inside `dt-ram`. The telemetry agent and twin have no mounted
ServiceAccount token. Do not weaken those settings to make a test pass.

## Verify event delivery and record a versioned trace

In separate terminals, forward the NATS and twin services, then start the
existing Member 3 collector from `services/prediction-service`. Use the Python
environment described in that service's README. The collector creates a durable
JetStream consumer and commits a sample before acknowledging it.

```powershell
kubectl port-forward -n dt-ram svc/nats 4222:4222
kubectl port-forward -n dt-ram svc/twin-manager 8080:8080
```

```powershell
cd services/prediction-service
python -m prediction_app.collector --db ../../datasets/raw/<RUN_ID>/node_samples.sqlite listen --nats-url nats://127.0.0.1:4222
```

Capture a baseline interval and, if a vetted bounded workload exists, a
separately timestamped load interval. For Teammate 3's default 60-second
history and 60-second horizon, aim for at least 30 minutes of contiguous
1-second observations per node. This is a collection target, not a guarantee
that a trace is scientifically adequate. Record the topology, node labels,
container image IDs, Git SHA, versions, sample interval, workload/fault
schedule, and any outages in a local run metadata file.

During collection, compare node IDs and recent timestamps from the collector
with `kubectl get pods -n dt-ram -o wide` and the twin's `/twin/state` response
through the port-forward. Twin freshness should turn stale when telemetry
stops. Fidelity remains disabled until it is measured from an independent
physical-versus-twin observation; matching an event to its own twin update is
not an independent fidelity check.
Compare CPU and memory with a timestamped independent `kubectl top nodes` or
Metrics API snapshot. In k3d, the Go agent can observe Docker/WSL2 host CPU
and memory under different node IDs, so node-specific fidelity and research
use must be assessed before giving the trace to a forecaster.

Stop the collector cleanly, then export from the same service directory:

```powershell
python -m prediction_app.collector --db ../../datasets/raw/<RUN_ID>/node_samples.sqlite export --output ../../datasets/processed/<RUN_ID>/node-events.jsonl --source-label k3d:<RUN_ID> --period-seconds 1
```

The export creates `node-events.jsonl.manifest.json` with the SHA-256 hash,
source label, time span, node IDs, sample count, and missing-bucket counts.
From the repository root, verify its actual bytes and quality fields:

```powershell
python infrastructure/testbed/verify_export.py datasets/processed/<RUN_ID>/node-events.jsonl --expected-nodes 3 --min-duration-seconds 1800 --max-missing-fraction 0.10
```

On Windows the current exporter may write CRLF bytes after hashing LF content.
If verification reports only that SHA-256 mismatch, rerun with
`--normalize-lf`. The verifier rewrites bytes **only** when the LF-normalized
file exactly matches the manifest hash; it rejects all other mismatches.
The 10% missing-bucket ceiling is an integration-trace gate, not a claim of
forecasting fitness; report the actual per-node gaps and sensor-fidelity
limits separately.

Recheck with `Get-FileHash -Algorithm SHA256`, replay the JSONL into a fresh
SQLite database, and compare counts and node IDs. Keep raw and processed
files in the ignored dataset directories. Share the versioned trace and
manifest through the team's approved artifact channel; the PR should contain
only its identifier, checksum, collection conditions, quality summary, and
handoff location. If no artifact channel exists, identify that handoff gap
rather than committing an ignored dataset.

## Application telemetry and safety handoff

Node events currently contain CPU, memory, and network utilization only.
`service_id`, request rate, p95 latency, queue depth, SLO, placement, and
migration state require a separately verified producer. The evidence and
proposed data contract are in [telemetry-contract.md](telemetry-contract.md).
The deployment and actuation findings belong in
[deployment-findings.md](deployment-findings.md). Do not publish an event or
train a model for a field that was not measured.
