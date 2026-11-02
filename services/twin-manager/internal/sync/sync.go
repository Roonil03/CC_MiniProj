// Package sync implements the twin synchronization cycle:
// Physical state -> Telemetry -> Normalize -> Timestamp -> Validate
// -> Twin state update.
package sync

import (
	"fmt"
	"math"
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
// Missing capacity stays unknown and missing health is explicitly unknown.
func (e *SyncEngine) ApplyTelemetry(t model.TelemetryIngest) (model.NodeState, error) {
	if t.NodeID == "" {
		return model.NodeState{}, fmt.Errorf("node_id is required")
	}
	if math.IsNaN(t.CPUUtil) || math.IsInf(t.CPUUtil, 0) || t.CPUUtil < 0 || t.CPUUtil > 1 {
		return model.NodeState{}, fmt.Errorf("cpu utilization must be in [0,1], got %v", t.CPUUtil)
	}
	if math.IsNaN(t.MemoryUtil) || math.IsInf(t.MemoryUtil, 0) || t.MemoryUtil < 0 || t.MemoryUtil > 1 {
		return model.NodeState{}, fmt.Errorf("memory utilization must be in [0,1], got %v", t.MemoryUtil)
	}
	for _, value := range []float64{t.NetworkInMbps, t.NetworkOutMbps, t.CPUTotalCores, t.MemoryTotalMB} {
		if math.IsNaN(value) || math.IsInf(value, 0) || value < 0 {
			return model.NodeState{}, fmt.Errorf("capacity and network metrics must be finite and nonnegative")
		}
	}
	ts := t.Timestamp.UTC()
	if ts.IsZero() {
		ts = e.now().UTC()
	}
	if ts.After(e.now().UTC()) {
		return model.NodeState{}, fmt.Errorf("telemetry timestamp is in the future")
	}
	cpuTotal := t.CPUTotalCores
	if cpuTotal <= 0 {
		if prev, ok := e.store.GetNode(t.NodeID); ok {
			cpuTotal = prev.CPUCoreTotal
		}
	}
	memTotal := t.MemoryTotalMB
	if memTotal <= 0 {
		if prev, ok := e.store.GetNode(t.NodeID); ok {
			memTotal = prev.MemoryTotalMB
		}
	}
	health := t.Health
	if health == "" {
		health = "unknown"
	}
	n := model.NodeState{
		NodeID:         t.NodeID,
		CPUCoreTotal:   cpuTotal,
		CPUUsedCores:   t.CPUUtil * cpuTotal,
		MemoryTotalMB:  memTotal,
		MemoryUsedMB:   t.MemoryUtil * memTotal,
		NetworkInMbps:  t.NetworkInMbps,
		NetworkOutMbps: t.NetworkOutMbps,
		Health:         health,
		Timestamp:      ts,
		Stale:          e.now().UTC().Sub(ts) > e.staleAfter,
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

// Nodes recomputes freshness at read time, including when telemetry stops.
func (e *SyncEngine) Nodes() []model.NodeState {
	nodes := e.store.ListNodes()
	for i := range nodes {
		nodes[i] = e.Refresh(nodes[i])
	}
	return nodes
}

func (e *SyncEngine) Refresh(n model.NodeState) model.NodeState {
	n.Stale = n.Timestamp.IsZero() || n.Timestamp.After(e.now()) || e.now().Sub(n.Timestamp) > e.staleAfter
	return n
}
