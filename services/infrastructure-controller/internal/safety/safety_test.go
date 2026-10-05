package safety_test

import (
	"testing"

	"dt-ram/infrastructure-controller/internal/config"
	"dt-ram/infrastructure-controller/internal/model"
	"dt-ram/infrastructure-controller/internal/safety"

	"github.com/stretchr/testify/require"
)

func testCfg() config.Config {
	cfg := config.Default()
	cfg.MinFidelity = 0.80
	cfg.MinPredictionConfidence = 0.80
	cfg.MaxSLOProb = 0.10
	cfg.MaxMigrationsPerMinute = 3
	return cfg
}

func approvedReq() model.DecisionRequest {
	return model.DecisionRequest{
		DecisionID: "d-1", PolicyVersion: "ppo-v1",
		Action:          model.Action{Type: "MIGRATE", Service: "processor", Source: "edge-a1", Destination: "edge-b1"},
		Predicted:       model.Predicted{LatencyMs: 20, CPUUtil: 0.6, SLOViolationProb: 0.04, PredictionConfidence: 0.9},
		DTFidelity:      0.97,
		DestinationFree: 2.0, DestinationOK: true, SourceHealthy: true,
	}
}

func TestApproveHealthyMigration(t *testing.T) {
	g := safety.New(testCfg())
	v := g.Evaluate(approvedReq())
	require.True(t, v.Approved)
}

func TestRejectStaleTwin(t *testing.T) {
	g := safety.New(testCfg())
	req := approvedReq()
	req.DTFidelity = 0.5
	v := g.Evaluate(req)
	require.False(t, v.Approved)
}

func TestRejectUnhealthyDestination(t *testing.T) {
	g := safety.New(testCfg())
	req := approvedReq()
	req.DestinationOK = false
	v := g.Evaluate(req)
	require.False(t, v.Approved)
}

func TestRejectHighSLOProbability(t *testing.T) {
	g := safety.New(testCfg())
	req := approvedReq()
	req.Predicted.SLOViolationProb = 0.5
	v := g.Evaluate(req)
	require.False(t, v.Approved)
}

func TestMigrationStormProtection(t *testing.T) {
	cfg := testCfg()
	cfg.MaxMigrationsPerMinute = 1
	g := safety.New(cfg)
	require.True(t, g.Evaluate(approvedReq()).Approved)
	g.RecordMigration("edge-a1")
	// Same source still in cooldown AND over storm budget.
	v := g.Evaluate(approvedReq())
	require.False(t, v.Approved)
}

func TestMigrationDurationEstimate(t *testing.T) {
	require.InDelta(t, 10.0, safety.MigrationDurationEstimate(100, 100, 2), 1e-9)
	require.Equal(t, -1.0, safety.MigrationDurationEstimate(100, 0, 2))
}
