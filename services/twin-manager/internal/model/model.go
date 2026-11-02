// Package model defines twin-manager schemas.
// Mirrors the node/workload state and telemetry event contracts.
package model

import "time"

// NodeState is the synchronized virtual representation of one K8s node.
type NodeState struct {
	NodeID            string    `json:"node_id"`
	Location          string    `json:"location"`
	CPUCoreTotal      float64   `json:"cpu_total"`
	CPUUsedCores      float64   `json:"cpu_used"`
	MemoryTotalMB     float64   `json:"memory_total_mb"`
	MemoryUsedMB      float64   `json:"memory_used_mb"`
	NetworkInMbps     float64   `json:"network_in_mbps"`
	NetworkOutMbps    float64   `json:"network_out_mbps"`
	LatencyToCloudMs  float64   `json:"latency_to_cloud_ms"`
	Health            string    `json:"health"`
	Timestamp         time.Time `json:"timestamp"`
	Stale             bool      `json:"stale"`
	Fidelity          float64   `json:"fidelity"`
}

// WorkloadState mirrors the service placement view.
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
	NodeID          string    `json:"node_id"`
	Timestamp       time.Time `json:"timestamp"`
}

// TelemetryIngest is the accepted POST /twin/update payload,
// compatible with the telemetry-agent NODE_METRIC_UPDATED event.
type TelemetryIngest struct {
	NodeID          string    `json:"node_id" binding:"required"`
	CPUUtil         float64   `json:"cpu"`
	MemoryUtil      float64   `json:"memory"`
	NetworkInMbps   float64   `json:"network_in"`
	NetworkOutMbps  float64   `json:"network_out"`
	CPUTotalCores   float64   `json:"cpu_total"`
	MemoryTotalMB   float64   `json:"memory_total_mb"`
	Health          string    `json:"health"`
	Timestamp       time.Time `json:"timestamp"`
}

// FidelityReport exposes the twin fidelity score.
type FidelityReport struct {
	NodeID        string    `json:"node_id"`
	Fidelity      float64   `json:"fidelity"`
	AutonomyLevel string    `json:"autonomy_level"`
	Stale         bool      `json:"stale"`
	EvaluatedAt   time.Time `json:"evaluated_at"`
}
