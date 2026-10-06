package sync

import (
	"dt-ram/twin-manager/internal/model"
	"dt-ram/twin-manager/internal/store"
	"math"
	"testing"
	"time"
)

func TestFreshnessAndOrdering(t *testing.T) {
	st := store.NewMemory()
	e := New(st, 5*time.Second)
	now := time.Now().UTC()
	e.now = func() time.Time { return now }
	sample := model.TelemetryIngest{NodeID: "node", Timestamp: now, CPUUtil: .5, MemoryUtil: .5, CPUTotalCores: 2, MemoryTotalMB: 1024}
	n, err := e.ApplyTelemetry(sample)
	if err != nil || n.Stale || n.CPUUsedCores != 1 || n.Health != "unknown" {
		t.Fatalf("unexpected node: %+v %v", n, err)
	}
	if _, err := e.ApplyTelemetry(sample); err == nil {
		t.Fatal("duplicate accepted")
	}
	sample.Timestamp = now.Add(-time.Second)
	if _, err := e.ApplyTelemetry(sample); err == nil {
		t.Fatal("old sample accepted")
	}
	now = now.Add(6 * time.Second)
	if !e.Nodes()[0].Stale {
		t.Fatal("stopped telemetry stayed fresh")
	}
}

func TestInvalidAndUnknownSignals(t *testing.T) {
	e := New(store.NewMemory(), 5*time.Second)
	for _, v := range []float64{math.NaN(), math.Inf(1), -1, 2} {
		if _, err := e.ApplyTelemetry(model.TelemetryIngest{NodeID: "node", CPUUtil: v}); err == nil {
			t.Fatalf("accepted %v", v)
		}
	}
	if _, err := e.ApplyTelemetry(model.TelemetryIngest{NodeID: "node", Timestamp: time.Now().Add(time.Hour)}); err == nil {
		t.Fatal("future accepted")
	}
	n, err := e.ApplyTelemetry(model.TelemetryIngest{NodeID: "node"})
	if err != nil || n.CPUCoreTotal != 0 || n.MemoryTotalMB != 0 {
		t.Fatal("invented capacity", n, err)
	}
}
