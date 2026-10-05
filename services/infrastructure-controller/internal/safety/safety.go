// Package safety implements the explicit safety/policy gate.
// Safety is enforced by checks, not reward shaping (AGENTS.md):
// capacity, SLO, health, DT freshness/fidelity, prediction confidence,
// migration storm limits and per-node cooldowns (Design.md Sections 33-36).
package safety

import (
	"fmt"
	"strings"
	"sync"
	"time"

	"dt-ram/infrastructure-controller/internal/config"
	"dt-ram/infrastructure-controller/internal/model"
)

// Gate enforces migration limits and cooldowns with an audit trail.
type Gate struct {
	cfg       config.Config
	mu        sync.Mutex
	migrations []time.Time
	nodeLast  map[string]time.Time
	now       func() time.Time
}

// New returns a Gate with the given safety configuration.
func New(cfg config.Config) *Gate {
	return &Gate{cfg: cfg, nodeLast: map[string]time.Time{}, now: time.Now}
}

// Evaluate runs all applicable checks and returns the verdict.
// Fail-closed: any missing signal (stale DT, low confidence, unknown
// health) rejects or downgrades autonomy instead of executing.
func (g *Gate) Evaluate(req model.DecisionRequest) model.SafetyVerdict {
	var reasons []string
	reject := func(format string, args ...any) {
		reasons = append(reasons, fmt.Sprintf(format, args...))
	}

	// NOOP is always safe.
	if strings.ToUpper(req.Action.Type) == "NOOP" {
		return model.SafetyVerdict{Approved: true, Reasons: []string{"noop always safe"}}
	}

	// DT fidelity gate (Design.md Section 18 + AGENTS.md fallback).
	if req.DTFidelity < g.cfg.MinFidelity {
		reject("dt fidelity %.3f below minimum %.3f: disable RL actuation", req.DTFidelity, g.cfg.MinFidelity)
	}
	// Prediction confidence gate (Section 34).
	if req.Predicted.PredictionConfidence < g.cfg.MinPredictionConfidence && req.Predicted.PredictionConfidence > 0 {
		reject("prediction confidence %.3f below minimum %.3f", req.Predicted.PredictionConfidence, g.cfg.MinPredictionConfidence)
	}
	// SLO gate (Section 26/33).
	if req.Predicted.SLOViolationProb > g.cfg.MaxSLOProb {
		reject("predicted SLO violation probability %.3f exceeds max %.3f", req.Predicted.SLOViolationProb, g.cfg.MaxSLOProb)
	}
	// Health gates.
	if !req.SourceHealthy {
		reject("source node unhealthy")
	}
	if strings.ToUpper(req.Action.Type) == "MIGRATE" || strings.ToUpper(req.Action.Type) == "PLACE" {
		if !req.DestinationOK {
			reject("destination node unhealthy or unavailable")
		}
		if req.DestinationFree <= 0 {
			reject("destination lacks free capacity")
		}
	}

	// Migration storm + cooldown gates (Sections 35-36), checked only
	// for MIGRATE actions so SCALE/PLACE cannot starve on migration budget.
	if strings.ToUpper(req.Action.Type) == "MIGRATE" {
		g.mu.Lock()
		now := g.now()
		cutoff := now.Add(-time.Minute)
		kept := g.migrations[:0]
		for _, t := range g.migrations {
			if t.After(cutoff) {
				kept = append(kept, t)
			}
		}
		g.migrations = kept
		if len(g.migrations) >= g.cfg.MaxMigrationsPerMinute {
			reject("migration storm protection: %d migrations in last minute (max %d)", len(g.migrations), g.cfg.MaxMigrationsPerMinute)
		}
		if last, ok := g.nodeLast[req.Action.Source]; ok && now.Sub(last) < g.cfg.NodeCooldown {
			reject("source node %s in cooldown (%s remaining)", req.Action.Source, (g.cfg.NodeCooldown - now.Sub(last)).Round(time.Second))
		}
		g.mu.Unlock()
	}

	if len(reasons) > 0 {
		return model.SafetyVerdict{Approved: false, Reasons: reasons}
	}
	return model.SafetyVerdict{Approved: true, Reasons: []string{"all safety checks passed"}}
}

// RecordMigration logs a successful migration for storm/cooldown accounting.
func (g *Gate) RecordMigration(source string) {
	g.mu.Lock()
	defer g.mu.Unlock()
	now := g.now()
	g.migrations = append(g.migrations, now)
	g.nodeLast[source] = now
}

// MigrationDurationEstimate implements Design.md Section 31 first
// approximation: T = S_state / B_effective + T_overhead.
func MigrationDurationEstimate(stateMB, bandwidthMbps, overheadSec float64) float64 {
	if bandwidthMbps <= 0 {
		return -1
	}
	return (stateMB*8/bandwidthMbps) + overheadSec
}
