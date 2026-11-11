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
	now := time.Now().UTC().Add(-2 * time.Second)
	e.now = func() time.Time { return now }
	sample := model.TelemetryIngest{NodeID: "node", Timestamp: now, CPUUtil: ptr(.5), MemoryUtil: ptr(.5), CPUTotalCores: ptr(2), MemoryTotalMB: ptr(1024)}
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
		if _, err := e.ApplyTelemetry(model.TelemetryIngest{NodeID: "node", CPUUtil: ptr(v), MemoryUtil: ptr(0)}); err == nil {
			t.Fatalf("accepted %v", v)
		}
	}
	if _, err := e.ApplyTelemetry(model.TelemetryIngest{NodeID: "node", Timestamp: time.Now().Add(time.Hour)}); err == nil {
		t.Fatal("future accepted")
	}
	n, err := e.ApplyTelemetry(model.TelemetryIngest{NodeID: "node"})
	if err == nil {
		t.Fatal("missing utilization was treated as a real zero", n)
	}
}

func TestMissingOptionalMetricPreservesPriorValueButExplicitZeroClearsIt(t *testing.T) {
	st := store.NewMemory()
	e := New(st, 5*time.Second)
	now := time.Now().UTC().Add(-2 * time.Second)
	first := model.TelemetryIngest{NodeID: "node", Timestamp: now, CPUUtil: ptr(.5), MemoryUtil: ptr(.25), CPUTotalCores: ptr(4), MemoryTotalMB: ptr(1000), NetworkInMbps: ptr(8)}
	if _, err := e.ApplyTelemetry(first); err != nil {
		t.Fatal(err)
	}
	next := model.TelemetryIngest{NodeID: "node", Timestamp: now.Add(time.Second), CPUUtil: ptr(0), MemoryUtil: ptr(0)}
	n, err := e.ApplyTelemetry(next)
	if err != nil || n.NetworkInMbps != 8 || n.CPUUsedCores != 0 {
		t.Fatalf("missing vs explicit zero lost: %+v %v", n, err)
	}
	next.Timestamp = now.Add(2 * time.Second)
	next.NetworkInMbps = ptr(0)
	n, err = e.ApplyTelemetry(next)
	if err != nil || n.NetworkInMbps != 0 {
		t.Fatalf("explicit zero not stored: %+v %v", n, err)
	}
}

func ptr(v float64) *float64 { return &v }
