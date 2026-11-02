// Package config loads infrastructure-controller settings.
// Defaults follow .env.example (port 8081) and service safety tunables.
// Never hard-code experiment parameters elsewhere.
package config

import (
	"os"
	"strconv"
	"time"
)

// Config holds controller runtime settings.
type Config struct {
	Port                    string
	NATSURL                 string
	DecisionSubject         string
	Kubeconfig              string
	Namespace               string
	MaxMigrationsPerMinute  int
	NodeCooldown            time.Duration
	MinPredictionConfidence float64
	MaxSLOProb              float64
	MinFidelity             float64
	DryRun                  bool
}

// Default returns safe defaults (dry-run-friendly, fail-closed).
func Default() Config {
	return Config{
		Port:                    envOr("INFRASTRUCTURE_CONTROLLER_PORT", "8081"),
		NATSURL:                 envOr("NATS_URL", "nats://localhost:4222"),
		DecisionSubject:         envOr("DECISION_SUBJECT", "dt.decisions.resource"),
		Kubeconfig:              envOr("KUBECONFIG_PATH", ""),
		Namespace:               envOr("K8S_NAMESPACE", "dt-ram"),
		MaxMigrationsPerMinute:  envIntOr("SAFETY_MAX_MIGRATIONS_PER_MIN", 3),
		NodeCooldown:            30 * time.Second,
		MinPredictionConfidence: 0.80,
		MaxSLOProb:              0.10,
		MinFidelity:             0.95,
		DryRun:                  envBoolOr("CONTROLLER_DRY_RUN", true),
	}
}

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func envIntOr(k string, d int) int {
	if v := os.Getenv(k); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return d
}

func envBoolOr(k string, d bool) bool {
	if v := os.Getenv(k); v != "" {
		if b, err := strconv.ParseBool(v); err == nil {
			return b
		}
	}
	return d
}
