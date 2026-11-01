# Application telemetry contract for review

This is a Member 2 handoff proposal, not an implemented publisher or NATS
subject. The only implemented high-frequency event is
`NODE_METRIC_UPDATED` on `dt.telemetry.node_metric`; the Go agent measures node
CPU/memory utilization and network throughput. The prediction collector
accepts those four measurements and does not infer application behavior.

The design's workload state and `twin-manager/internal/model.WorkloadState`
already name `service_id`, `replicas`, `cpu_request`, `memory_request_mb`,
`cpu_usage`, `memory_usage_mb`, `request_rate`, `p95_latency_ms`, `slo_ms`,
`node_id`, and `timestamp`. No code in the current workload directories emits
these measurements. The table separates observable configuration from metrics
that need instrumentation.

| Field | Required source and interpretation | Current state |
| --- | --- | --- |
| `timestamp` | RFC3339 UTC observation or completed aggregation-window end | Present in node events; no workload producer |
| `service_id` | Stable workload/Service identifier, mapped to namespace and pod labels | Model field only |
| `node_id`, placement | Kubernetes Pod `spec.nodeName` and a versioned pod-to-service mapping | Read-only PodList exists in the controller; no time-series sink |
| `replicas` | Deployment desired/available replica counts, clearly distinguished | Model field only |
| `cpu_request`, `memory_request_mb` | Pod resource requests from the Kubernetes API; agree on cores and decimal MB versus MiB conversion | Read-only PodList exists; no workload event |
| `cpu_usage`, `memory_usage_mb` | Timestamped per-pod measurements from a verified metrics source, aggregated by service | k3d's K3s distribution provides metrics-server, but this repository has no app-usage producer or time-series sink |
| `request_rate` | Delta of an application request counter divided by its measured window, in requests/second | No application counter instrumentation |
| `p95_latency_ms` | Server-side latency histogram quantile over a stated window, in milliseconds; include request count | No application latency histogram |
| queue depth | Application queue gauge with queue/service identity and observation time, in items | Not in the current workload model or node event |
| `slo_ms` | Versioned service objective/configuration, in milliseconds; not inferred from observed latency | Model field only |
| migration state | Explicit intent, start, completion, failure, and rollback timestamps tied to decision ID | Live migration is unavailable |

Before any event or schema is added, Teammates 1, 3, and 4 should agree on
service IDs, exact units, a common UTC time basis, aggregation windows,
missing-value semantics, and how replica changes and pod restarts affect
series identity. A service-level p95 must be calculated from a merged
histogram or raw observations, not by averaging pod p95 values. Missing
measurements must remain missing; zero has a different meaning.

Once a real producer exists, validate it against an independently observed
request schedule and Kubernetes Pod/Deployment snapshots. Record sample
coverage, histogram counts, clock skew, unit conversions, and the source
version in the dataset manifest. Until then, only node CPU/memory/network are
valid prediction targets from this stream, and latency/SLO claims remain
unsupported by measured application data.
