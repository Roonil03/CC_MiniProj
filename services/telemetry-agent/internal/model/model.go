// Package model defines the DT-RAM telemetry schemas owned by Member-2.
//
// Schemas follow Design.md Section 16 (node/workload state) and
// Section 53 (NODE_METRIC_UPDATED event). Field names are stable
// contracts shared with twin-manager and infrastructure-controller.
package model

import "time"

// NodeState mirrors Design.md Section 16 node representation.
type NodeState struct {
	NodeID           string    `json:"node_id"`
	Location         string    `json:"location"`
	CPUCoreTotal     float64   `json:"cpu_total"`
	CPUUsedCores     float64   `json:"cpu_used"`
	MemoryTotalMB    float64   `json:"memory_total_mb"`
	MemoryUsedMB     float64   `json:"memory_used_mb"`
	NetworkInMbps    float64   `json:"network_in_mbps"`
	NetworkOutMbps   float64   `json:"network_out_mbps"`
	LatencyToCloudMs float64   `json:"latency_to_cloud_ms"`
	Health           string    `json:"health"`
	Timestamp        time.Time `json:"timestamp"`
}

// WorkloadState mirrors Design.md Section 16 workload representation.
type WorkloadState struct {
	ServiceID       string    `json:"service_id"`
	Replicas        int       `json:"replicas"`
	CPURequest      float64   `json:"cpu_request"`
	MemoryRequestMB float64   `json:"memory_request_mb"`
	CPUUsage        float64   `json:"cpu_usage"`
	MemoryUsageMB   float64   `json:"memory_usage_mb"`
	RequestRate     float64   `json:"request_rate"`
	P95LatencyMs    float64   `json:"p95_latency_ms"`
	SLOMs           float64   `json:"slo_ms"`
	Timestamp       time.Time `json:"timestamp"`
}

// NodeMetrics is the high-frequency sample collected by the agent.
type NodeMetrics struct {
	CPUTotalCores  float64 `json:"cpu_total"`
	MemoryTotalMB  float64 `json:"memory_total_mb"`
	CPUUtil        float64 `json:"cpu"`         // 0..1
	MemoryUtil     float64 `json:"memory"`      // 0..1
	NetworkInMbps  float64 `json:"network_in"`  // Mbps
	NetworkOutMbps float64 `json:"network_out"` // Mbps
}

// NodeMetricEvent is the NATS event per Design.md Section 53.
type NodeMetricEvent struct {
	EventType string      `json:"event_type"`
	Timestamp time.Time   `json:"timestamp"`
	NodeID    string      `json:"node_id"`
	Metrics   NodeMetrics `json:"metrics"`
}

// NewNodeMetricEvent builds a NODE_METRIC_UPDATED event.
func NewNodeMetricEvent(nodeID string, m NodeMetrics, ts time.Time) NodeMetricEvent {
	if ts.IsZero() {
		ts = time.Now().UTC()
	}
	return NodeMetricEvent{
		EventType: "NODE_METRIC_UPDATED",
		Timestamp: ts.UTC(),
		NodeID:    nodeID,
		Metrics:   m,
	}
}
