// Package config loads twin-manager settings.
// Defaults follow .env.example (TWIN_MANAGER_PORT=8080) and
// Design.md Section 58 thresholds.
package config

import (
	"os"
	"strconv"
	"time"
)

// Config holds twin-manager runtime settings.
type Config struct {
	Port               string
	NATSURL            string
	SubscribeSubject   string
	RedisAddr          string
	StaleAfter         time.Duration
	FidelityAutonomous float64
	FidelityRestricted float64
	FidelitySimOnly    float64
}

// Default returns local-development defaults.
func Default() Config {
	return Config{
		Port:               envOr("TWIN_MANAGER_PORT", "8080"),
		NATSURL:            envOr("NATS_URL", "nats://localhost:4222"),
		SubscribeSubject:   envOr("TWIN_SUBJECT", "dt.telemetry.node_metric"),
		RedisAddr:          envOr("REDIS_ADDR", ""),
		StaleAfter:         5 * time.Second,
		FidelityAutonomous: 0.95,
		FidelityRestricted: 0.90,
		FidelitySimOnly:    0.80,
	}
}

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func envFloatOr(k string, d float64) float64 {
	if v := os.Getenv(k); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return d
}
