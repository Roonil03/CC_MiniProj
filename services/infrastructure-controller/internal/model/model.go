// Package model defines infrastructure-controller schemas.
// Action encoding follows Design.md Section 24; decision events follow
// Section 54. Only validated + safety-approved actions reach Kubernetes.
package model

import "time"

// Action is one candidate resource-management action.
type Action struct {
	Type        string `json:"type"`
	Service     string `json:"service"`
	Source      string `json:"source,omitempty"`
	Destination string `json:"destination,omitempty"`
	Replicas    *int   `json:"replicas,omitempty"`
	CPUDelta    float64 `json:"cpu_delta,omitempty"`
	MemoryDelta float64 `json:"memory_delta_mb,omitempty"`
}

// Predicted captures the simulator/RL expectation attached to a decision.
type Predicted struct {
	LatencyMs             float64 `json:"latency"`
	CPUUtil               float64 `json:"cpu"`
	SLOViolationProb      float64 `json:"slo_violation_probability"`
	PredictionConfidence  float64 `json:"prediction_confidence"`
}

// DecisionRequest is the gated actuation input.
type DecisionRequest struct {
	DecisionID      string   `json:"decision_id"`
	PolicyVersion   string   `json:"policy_version"`
	Action          Action   `json:"action"`
	Predicted       Predicted `json:"predicted"`
	DTFidelity      float64  `json:"dt_fidelity"`
	DestinationFree float64  `json:"destination_free_cpu"`
	DestinationOK   bool     `json:"destination_healthy"`
	SourceHealthy   bool     `json:"source_healthy"`
	DryRun          bool     `json:"dry_run,omitempty"`
}

// SafetyVerdict is the gate outcome.
type SafetyVerdict struct {
	Approved bool     `json:"approved"`
	Reasons  []string `json:"reasons"`
}

// ActionRecord is the audit-log entry for every gated decision.
type ActionRecord struct {
	DecisionID string        `json:"decision_id"`
	Action     Action        `json:"action"`
	Verdict    SafetyVerdict `json:"safety"`
	Executed   bool          `json:"executed"`
	DryRun     bool          `json:"dry_run"`
	At         time.Time     `json:"at"`
	Message    string        `json:"message,omitempty"`
}

// NodeCapacity describes destination headroom for capacity checks.
type NodeCapacity struct {
	NodeID    string  `json:"node_id"`
	FreeCPU   float64 `json:"free_cpu_cores"`
	FreeMemMB float64 `json:"free_mem_mb"`
	Healthy   bool    `json:"healthy"`
}
