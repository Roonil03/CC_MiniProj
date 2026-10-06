package config

import (
	"fmt"
	"gopkg.in/yaml.v3"
	"os"
	"time"
)

func Load(path string) (Config, error) {
	cfg := Default()
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return cfg, nil
	}
	if err != nil {
		return cfg, err
	}
	var doc struct {
		Twin struct {
			Stale int `yaml:"stale_after_seconds"`
		} `yaml:"digital_twin"`
	}
	if err := yaml.Unmarshal(data, &doc); err != nil {
		return cfg, err
	}
	if doc.Twin.Stale <= 0 {
		return cfg, fmt.Errorf("stale_after_seconds must be positive")
	}
	cfg.StaleAfter = time.Duration(doc.Twin.Stale) * time.Second
	return cfg, nil
}
