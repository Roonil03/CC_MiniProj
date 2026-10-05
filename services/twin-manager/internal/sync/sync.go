// Package sync implements the twin synchronization cycle:
// Physical state -> Telemetry -> Normalize -> Timestamp -> Validate
// -> Twin state update (Design.md Section 17).
package sync

import (
	"fmt"
	"time"

	"dt-ram/twin-manager/internal/model"
	"dt-ram/twin-manager/internal/store"
)

// SyncEngine applies telemetry updates to the twin store.
type SyncEngine struct {
	store      store.Store
	staleAfter time.Duration
	now        func() time.Time
}

// New returns a SyncEngine backed by the given store.
func New(s store.Store, staleAfter time.Duration) *SyncEngine {
	return &SyncEngine{store: s, staleAfter: staleAfter, now: time.Now}
}

// ApplyTelemetry validates, timestamps and stores one telemetry sample.
// Unknown nodes are created with defaults; health defaults to healthy.
func (e *SyncEngine) ApplyTelemetry(t model.TelemetryIngest) (model.NodeState, error) {
	if t.NodeID == "" {
		return model.NodeState{}, fmt.Errorf("node_id is required")
	}
	if t.CPUUtil < 0 || t.CPUUtil > 1 {
		return model.NodeState{}, fmt.Errorf("cpu utilization must be in [0,1], got %v", t.CPUUtil)
	}
	if t.MemoryUtil < 0 || t.MemoryUtil > 1 {
		return model.NodeState{}, fmt.Errorf("memory utilization must be in [0,1], got %v", t.MemoryUtil)
	}
	ts := t.Timestamp.UTC()
	if ts.IsZero() {
		ts = e.now().UTC()
	}
	cpuTotal := t.CPUTotalCores
	if cpuTotal <= 0 {
		cpuTotal = 8
	}
	memTotal := t.MemoryTotalMB
	if memTotal <= 0 {
		memTotal = 16384
	}
	health := t.Health
	if health == "" {
		health = "healthy"
	}
	n := model.NodeState{
		NodeID:           t.NodeID,
		CPUCoreTotal:     cpuTotal,
		CPUUsedCores:     t.CPUUtil * cpuTotal,
		MemoryTotalMB:    memTotal,
		MemoryUsedMB:     t.MemoryUtil * memTotal,
		NetworkInMbps:    t.NetworkInMbps,
		NetworkOutMbps:   t.NetworkOutMbps,
		Health:           health,
		Timestamp:        ts,
		Stale:            e.now().UTC().Sub(ts) > e.staleAfter,
	}
	// Preserve location on updates.
	if prev, ok := e.store.GetNode(t.NodeID); ok {
		n.Location = prev.Location
		n.LatencyToCloudMs = prev.LatencyToCloudMs
	}
	if err := e.store.UpsertNode(n); err != nil {
		return model.NodeState{}, err
	}
	return n, nil
}
