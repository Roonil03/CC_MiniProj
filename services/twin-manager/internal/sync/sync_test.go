package sync_test

import (
	"testing"
	"time"

	"dt-ram/twin-manager/internal/model"
	twinsync "dt-ram/twin-manager/internal/sync"
	"dt-ram/twin-manager/internal/store"

	"github.com/stretchr/testify/require"
)

func TestApplyTelemetryRejectsStaleOldTimestamp(t *testing.T) {
	st := store.NewMemory()
	e := twinsync.New(st, 5*time.Second)
	_, err := e.ApplyTelemetry(model.TelemetryIngest{NodeID: "", CPUUtil: 0.5, MemoryUtil: 0.5})
	require.Error(t, err)

	n, err := e.ApplyTelemetry(model.TelemetryIngest{
		NodeID: "edge-a1", CPUUtil: 0.5, MemoryUtil: 0.25,
		NetworkInMbps: 10, Timestamp: time.Now().UTC().Add(-time.Hour),
	})
	require.NoError(t, err)
	require.True(t, n.Stale)
}

func TestApplyTelemetryRejectsOutOfRange(t *testing.T) {
	st := store.NewMemory()
	e := twinsync.New(st, 5*time.Second)
	_, err := e.ApplyTelemetry(model.TelemetryIngest{NodeID: "edge-a1", CPUUtil: 2.0, MemoryUtil: 0.1})
	require.Error(t, err)
}
