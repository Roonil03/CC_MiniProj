package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestSafetyConfig(t *testing.T) {
	path := filepath.Join(t.TempDir(), "config.yaml")
	write := func(body string) {
		t.Helper()
		if err := os.WriteFile(path, []byte(body), 0600); err != nil {
			t.Fatal(err)
		}
	}
	write("safety:\n  max_migrations_per_minute: 2\n  minimum_prediction_confidence: 0.9\n  max_slo_probability: 0.05\n")
	t.Setenv("SAFETY_MAX_MIGRATIONS_PER_MIN", "")
	cfg, err := Load(path)
	if err != nil || cfg.MaxMigrationsPerMinute != 2 || cfg.MinPredictionConfidence != .9 || cfg.MaxSLOProb != .05 {
		t.Fatal(cfg, err)
	}
	t.Setenv("SAFETY_MAX_MIGRATIONS_PER_MIN", "1")
	cfg, err = Load(path)
	if err != nil || cfg.MaxMigrationsPerMinute != 1 {
		t.Fatal(cfg, err)
	}
	write("safety:\n  minimum_prediction_confidence: 0.1\n")
	if _, err := Load(path); err == nil {
		t.Fatal("unsafe config accepted")
	}
	t.Setenv("SAFETY_MAX_MIGRATIONS_PER_MIN", "invalid")
	if _, err := Load("missing.yaml"); err == nil {
		t.Fatal("bad env accepted")
	}
}
