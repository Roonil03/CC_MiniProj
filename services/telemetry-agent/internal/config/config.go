// Package config loads telemetry-agent configuration.
// Precedence: defaults < configs/config.yaml < environment variables.
// Port defaults follow .env.example (TELEMETRY_AGENT_PORT=8082).
package config

import (
	"os"
	"strconv"
	"time"
)

// Config holds runtime configuration for telemetry-agent.
type Config struct {
	NodeID         string
	Location       string
	Port           string
	NATSURL        string
	PublishSubject string
	CPUPoll        time.Duration
	MemPoll        time.Duration
	NetPoll        time.Duration
	PublishEnabled bool
}

// Default returns safe local-development defaults.
func Default() Config {
	return Config{
		NodeID:         envOr("TELEMETRY_NODE_ID", "edge-a1"),
		Location:       envOr("TELEMETRY_LOCATION", "edge-zone-a"),
		Port:           envOr("TELEMETRY_AGENT_PORT", "8082"),
		NATSURL:        envOr("NATS_URL", "nats://localhost:4222"),
		PublishSubject: envOr("TELEMETRY_SUBJECT", "dt.telemetry.node_metric"),
		CPUPoll:        1 * time.Second,
		MemPoll:        1 * time.Second,
		NetPoll:        1 * time.Second,
		PublishEnabled: envBoolOr("TELEMETRY_PUBLISH_ENABLED", false),
	}
}

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func envBoolOr(k string, d bool) bool {
	v := os.Getenv(k)
	if v == "" {
		return d
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return d
	}
	return b
}
