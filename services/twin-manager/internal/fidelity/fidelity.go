// Package fidelity implements the DT fidelity score from Design.md Section 18:
//
//	F_t = 1 - sum(w_i * |x_physical - x_twin|) / sum(w_i * Z_i)
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
	twinCPU := 0.0
	if twin.CPUCoreTotal > 0 {
		twinCPU = twin.CPUUsedCores / twin.CPUCoreTotal
	}
	twinMem := 0.0
	if twin.MemoryTotalMB > 0 {
		twinMem = twin.MemoryUsedMB / twin.MemoryTotalMB
	}
	num := weights["cpu"]*math.Abs(physicalCPU-twinCPU) +
		weights["memory"]*math.Abs(physicalMem-twinMem) +
		weights["network_in"]*math.Abs(physicalNetIn-twin.NetworkInMbps) +
		weights["network_out"]*math.Abs(physicalNetOut-twin.NetworkOutMbps)
	den := weights["cpu"]*norms["cpu"] + weights["memory"]*norms["memory"] +
		weights["network_in"]*norms["network_in"] + weights["network_out"]*norms["network_out"]
	if den <= 0 {
		return 0
	}
	f := 1 - num/den
	return math.Max(0, math.Min(1, f))
}

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
