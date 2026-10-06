package config

import (
	"fmt"
	"gopkg.in/yaml.v3"
	"math"
	"os"
	"strconv"
)

func Load(path string) (Config, error) {
	cfg := Default()
	data, err := os.ReadFile(path)
	if err != nil && !os.IsNotExist(err) {
		return cfg, err
	}
	if err == nil {
		var doc struct {
			Safety struct {
				Max        int     `yaml:"max_migrations_per_minute"`
				Confidence float64 `yaml:"minimum_prediction_confidence"`
				SLO        float64 `yaml:"max_slo_probability"`
			} `yaml:"safety"`
		}
		if err := yaml.Unmarshal(data, &doc); err != nil {
			return cfg, err
		}
		cfg.MaxMigrationsPerMinute = doc.Safety.Max
		cfg.MinPredictionConfidence = doc.Safety.Confidence
		cfg.MaxSLOProb = doc.Safety.SLO
	}
	if value := os.Getenv("SAFETY_MAX_MIGRATIONS_PER_MIN"); value != "" {
		n, err := strconv.Atoi(value)
		if err != nil {
			return cfg, err
		}
		cfg.MaxMigrationsPerMinute = n
	}
	if cfg.MaxMigrationsPerMinute <= 0 || math.IsNaN(cfg.MinPredictionConfidence) || cfg.MinPredictionConfidence < .80 || cfg.MinPredictionConfidence > 1 || math.IsNaN(cfg.MaxSLOProb) || cfg.MaxSLOProb < 0 || cfg.MaxSLOProb > .10 {
		return cfg, fmt.Errorf("invalid safety settings: positive migration budget, confidence in [0.80,1], SLO probability in [0,0.10] required")
	}
	return cfg, nil
}
