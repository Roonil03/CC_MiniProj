package config

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestFreshnessConfig(t *testing.T) {
	path := filepath.Join(t.TempDir(), "config.yaml")
	if err := os.WriteFile(path, []byte("digital_twin:\n  stale_after_seconds: 3\n"), 0600); err != nil {
		t.Fatal(err)
	}
	cfg, err := Load(path)
	if err != nil || cfg.StaleAfter != 3*time.Second {
		t.Fatal(cfg, err)
	}
	if err := os.WriteFile(path, []byte("digital_twin:\n  stale_after_seconds: -1\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(path); err == nil {
		t.Fatal("negative freshness accepted")
	}
}
