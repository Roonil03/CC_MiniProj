package config

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestSamplingConfig(t *testing.T) {
	path := filepath.Join(t.TempDir(), "config.yaml")
	if err := os.WriteFile(path, []byte("telemetry:\n  cpu_interval_seconds: 2\n  memory_interval_seconds: 2\n  network_interval_seconds: 2\n"), 0600); err != nil {
		t.Fatal(err)
	}
	cfg, err := Load(path)
	if err != nil || cfg.CPUPoll != 2*time.Second {
		t.Fatal(cfg, err)
	}
	if err := os.WriteFile(path, []byte("telemetry: {}"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(path); err == nil {
		t.Fatal("zero poll accepted")
	}
}
