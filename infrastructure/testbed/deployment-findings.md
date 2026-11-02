# Member 2 testbed validation — 2026-11-01

## Scope and provenance

- Base commit: `712516dc7c381a6f1ff24e24f7781021118b972a` on `main`.
- Validation branch: `feature/member2-testbed-validation`.
- Local context: `k3d-dt-ram`, K3s `v1.32.5+k3s1` in Docker Desktop Linux/WSL2; one server and two agents. The server is labeled `cloud/cloud`, the agents `edge/edge-a` and `edge/edge-b` by `infrastructure/k3s/k3d.yaml`.
- This is a containerized integration testbed. It is not a physical edge-cluster measurement or an application workload experiment.
- Collection run ID: `k3d-20261101T122151Z-712516d`. The local raw SQLite trace is under `datasets/raw/<RUN_ID>/`; the processed JSONL and its sidecar are under `datasets/processed/<RUN_ID>/`. Both directories are ignored by Git. A non-secret copy of the manifest is tracked as [manifests/k3d-20261101T122151Z-712516d.json](manifests/k3d-20261101T122151Z-712516d.json).
- `run-metadata.json` in that ignored processed directory records the deployed image IDs, node topology, target sample period, and idle/no-fault schedule. `fidelity-reference.json` records a timestamped metrics-server versus twin snapshot without treating their different measurement scopes as an authoritative fidelity score.

## Deployment and observed behavior

The three k3d nodes were `Ready` with the intended labels. The existing NATS and Redis StatefulSets, three telemetry DaemonSet pods, twin-manager, and infrastructure-controller all reached `1/1 Running` with zero restarts at the rollout check. Each telemetry pod landed on a different node. Both 1Gi NATS/Redis PVCs were `Bound` on the k3d `local-path` StorageClass. All three Go images were built from the repository Dockerfiles and imported into k3d before applying `10-go-services.yaml`.

The agents published `NODE_METRIC_UPDATED` on the implemented JetStream subject. The twin `/twin/state` returned three fresh node IDs matching Kubernetes node names, and the existing prediction collector stored records for all three IDs in SQLite through a localhost NATS port-forward. At the same observation, `/twin/fidelity` reported `fidelity: 0` and `autonomy_level: disabled` for each node. No workload state was present.

The controller's in-cluster startup log confirmed `CONTROLLER_DRY_RUN=true` and `executor=logging`. Its read-only endpoints returned three Kubernetes nodes and seven pods in `dt-ram`. A synthetic shadow-only SCALE request with actual `dt_fidelity=0` returned HTTP 422, `approved=false`, `executed=false`, and a low-fidelity reason. No deployment was changed. The applied controller deployment still had `CONTROLLER_DRY_RUN=true`. `kubectl auth can-i` confirmed its ServiceAccount can list nodes and update deployments in `dt-ram`, but cannot update deployments in `kube-system` or read secrets in `dt-ram`. These are permission checks, not live actions.

## Independent telemetry check and suitability

The k3d agents use `gopsutil` host CPU and memory observations plus host-network counters, with a Kubernetes node name supplied by the DaemonSet. In this Docker/WSL2 setup, host CPU and memory are shared across the k3d node containers. At one twin snapshot all three reported `cpu_total=12`, `memory_total_mb=7609.1953125`, and `memory_used_mb=1916.2421875`. In contrast, the independent K3s metrics-server snapshot at about 12:24 UTC reported memory usage of `227196Ki` on agent-0, `249500Ki` on agent-1, and `658048Ki` on server-0, and distinct CPU usage (`23653458n`, `35022754n`, `72834994n`). The different measurement scopes prevent a valid node-by-node fidelity score. The twin correctly remains at fidelity zero.

The trace is therefore evidence that real measurements can traverse agent → JetStream → twin/collector, and can be used for pipeline or benchmark software checks with explicit provenance. It is **not** a validated three-independent-node workload trace for forecasting research or model activation. Node-specific collection on physical K3s hardware, or a separately validated Kubernetes node-metrics source, remains necessary for that claim. No synthetic application latency, workload, or SLO values were added to the trace.

## Dataset quality and handoff

The idle/no-fault run spans `2026-11-01T12:20:47.963363Z` to `12:51:04.793916Z` (1816.831 seconds). It contains 5,004 events, exactly 1,668 per node. Each node has 1,662 occupied one-second buckets and 156 missing buckets within its span (8.58%). The mean observed interval is 1.0899 seconds and the largest gap is 9.557 seconds. Thus the trace meets the documented 30-minute and 10% integration gates, but it is not a gap-free 1 Hz time series.

The collector's Windows export initially used CRLF file bytes while its manifest hash covered LF bytes. `verify_export.py --normalize-lf` rewrote the file only after the normalized bytes matched the manifest; a subsequent verification without normalization and `Get-FileHash` both matched SHA-256 `acbbdfed5414a141d186c215bc95bc9dbb6179d228c783609377e8a0d9931f4f`. Import into a fresh SQLite database returned `added=5004, total=5004`. This workaround does not change the event values. The exporter mismatch belongs to Member 3's collector; this PR leaves that component untouched.

The dataset and raw SQLite database remain local because `.gitignore` excludes them. The local archive is `local-dev/artifacts/k3d-20261101T122151Z-712516d.zip`, SHA-256 `cc9f51bd93a33a1ecbd05fa9e9ab5c97b660003ae32d67845007a2744837a985`; it contains the raw SQLite database, processed JSONL, collector manifest, run metadata, and independent metrics-server/twin snapshot. ZIP integrity passed. Transfer through a team-approved artifact channel is still needed before another machine can use it.

## Safety and actuation gaps

| Area | Current evidence and required follow-up before physical actuation |
| --- | --- |
| Independent twin fidelity | The twin exposes zero fidelity because no independent physical-versus-twin comparison feeds it. The k3d host-scoped mismatch above must be resolved and an external reference, threshold, and freshness policy validated. |
| Workload/SLO telemetry | The twin workload list is empty; node events carry CPU, memory, and network only. Instrument request counts, latency histograms, SLO objectives, placement, and per-pod usage per [telemetry-contract.md](telemetry-contract.md), then validate units and coverage against an observed workload. |
| Prediction and simulation | The controller request includes confidence, predicted SLO probability, and a reported fidelity value, but does not fetch authoritative twin/prediction/simulation evidence before a decision. Bind decisions to fresh, independently verified state and counterfactual results. |
| Migration, placement, and rollback | The executor rejects MIGRATE/PLACE and RESOURCE_ADJUST is not implemented. Define workload/storage compatibility, destination capacity and network checks, rollout observation, failed-action detection, rollback, and measured migration cost before enabling these actions. |
| Durable audit and idempotency | Decision records and duplicate IDs are process-local. Persist immutable decision inputs, safety verdicts, Kubernetes effects, and outcomes, with restart-safe idempotency and recovery. |
| Authentication and RBAC | The controller's service token is optional and is not configured in this manifest. The ServiceAccount can update deployments/scales within `dt-ram`, so the dry-run and live-actuation block are essential. Add authenticated caller identity, network access controls, and separately reviewed least privilege before any live mode. |
| Metrics and operations | NATS/Redis have PVCs in this local testbed, but no long-term historical event sink or application Prometheus metrics are wired. Define retention, recovery, alerting, and outage behavior for a physical deployment. |

Physical actuation remains disabled. This validation does not authorize removing the dry-run setting or the controller's live-action block.
