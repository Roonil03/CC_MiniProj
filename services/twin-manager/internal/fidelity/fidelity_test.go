package fidelity_test

import (
	"testing"

	"dt-ram/twin-manager/internal/fidelity"
	"dt-ram/twin-manager/internal/model"

	"github.com/stretchr/testify/require"
)

func TestScorePerfectMatchIsOne(t *testing.T) {
	twin := model.NodeState{NodeID: "edge-a1", CPUCoreTotal: 8, CPUUsedCores: 4, MemoryTotalMB: 16384, MemoryUsedMB: 8192, NetworkInMbps: 100, NetworkOutMbps: 100}
	f := fidelity.Score(0.5, 0.5, 100, 100, twin)
	require.InDelta(t, 1.0, f, 1e-9)
}

func TestAutonomyLevels(t *testing.T) {
	require.Equal(t, "autonomous", fidelity.AutonomyLevel(0.97, false))
	require.Equal(t, "restricted", fidelity.AutonomyLevel(0.92, false))
	require.Equal(t, "simulation-only", fidelity.AutonomyLevel(0.85, false))
	require.Equal(t, "disabled", fidelity.AutonomyLevel(0.5, false))
	require.Equal(t, "disabled-stale", fidelity.AutonomyLevel(0.99, true))
}
