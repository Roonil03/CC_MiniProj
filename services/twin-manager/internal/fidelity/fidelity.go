// Package fidelity implements the DT fidelity score:
//
//	F_t = 1 - sum(w_i * min(1, |x_physical - x_twin| / Z_i)) / sum(w_i)
//
// Autonomy mapping:
// >0.95 autonomous, 0.90-0.95 restricted, 0.80-0.90 simulation-only, <0.80 disabled.
package fidelity

import (
	"math"
	"time"

	"dt-ram/twin-manager/internal/model"
)

// Weights and normalization factors for the default metric set.
var (
	weights = map[string]float64{"cpu": 1.0, "memory": 1.0, "network_in": 0.5, "network_out": 0.5}
	norms   = map[string]float64{"cpu": 1.0, "memory": 1.0, "network_in": 1000.0, "network_out": 1000.0}
)

// Score compares a physical sample against the stored twin node.
func Score(physicalCPU, physicalMem, physicalNetIn, physicalNetOut float64, twin model.NodeState) float64 {
	// Missing capacities make utilization unknowable; treating it as zero would
	// award high fidelity to an uninitialized twin. Invalid samples fail closed.
	if !unit(physicalCPU) || !unit(physicalMem) || !finiteNonnegative(physicalNetIn) || !finiteNonnegative(physicalNetOut) ||
		!finitePositive(twin.CPUCoreTotal) || !finitePositive(twin.MemoryTotalMB) {
		return 0
	}
	twinCPU := twin.CPUUsedCores / twin.CPUCoreTotal
	twinMem := twin.MemoryUsedMB / twin.MemoryTotalMB
	if !unit(twinCPU) || !unit(twinMem) || !finiteNonnegative(twin.NetworkInMbps) || !finiteNonnegative(twin.NetworkOutMbps) {
		return 0
	}
	// Normalize each residual before weighting. A raw network-unit scale must
	// never drown out a full CPU/memory mismatch.
	num := weights["cpu"]*math.Min(1, math.Abs(physicalCPU-twinCPU)/norms["cpu"]) +
		weights["memory"]*math.Min(1, math.Abs(physicalMem-twinMem)/norms["memory"]) +
		weights["network_in"]*math.Min(1, math.Abs(physicalNetIn-twin.NetworkInMbps)/norms["network_in"]) +
		weights["network_out"]*math.Min(1, math.Abs(physicalNetOut-twin.NetworkOutMbps)/norms["network_out"])
	den := weights["cpu"] + weights["memory"] + weights["network_in"] + weights["network_out"]
	if den <= 0 {
		return 0
	}
	f := 1 - num/den
	return math.Max(0, math.Min(1, f))
}

func unit(v float64) bool              { return !math.IsNaN(v) && !math.IsInf(v, 0) && v >= 0 && v <= 1 }
func finiteNonnegative(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) && v >= 0 }
func finitePositive(v float64) bool    { return finiteNonnegative(v) && v > 0 }

// AutonomyLevel maps a fidelity score to a control mode.
func AutonomyLevel(f float64, stale bool) string {
	if stale {
		return "disabled-stale"
	}
	switch {
	case f > 0.95:
		return "autonomous"
	case f >= 0.90:
		return "restricted"
	case f >= 0.80:
		return "simulation-only"
	default:
		return "disabled"
	}
}

// Report builds a FidelityReport for a node.
func Report(n model.NodeState) model.FidelityReport {
	return model.FidelityReport{
		NodeID:        n.NodeID,
		Fidelity:      n.Fidelity,
		AutonomyLevel: AutonomyLevel(n.Fidelity, n.Stale),
		Stale:         n.Stale,
		EvaluatedAt:   time.Now().UTC(),
	}
}
