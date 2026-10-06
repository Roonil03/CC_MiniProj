package config

import (
	"fmt"
	"gopkg.in/yaml.v3"
	"os"
	"time"
)

// Load reads optional service tunables; identity/transport settings stay in env.
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
		Telemetry struct {
			CPU     int `yaml:"cpu_interval_seconds"`
			Memory  int `yaml:"memory_interval_seconds"`
			Network int `yaml:"network_interval_seconds"`
		} `yaml:"telemetry"`
	}
	if err := yaml.Unmarshal(data, &doc); err != nil {
		return cfg, err
	}
	if doc.Telemetry.CPU <= 0 || doc.Telemetry.CPU != doc.Telemetry.Memory || doc.Telemetry.CPU != doc.Telemetry.Network {
		return cfg, fmt.Errorf("combined sampler requires equal positive CPU/memory/network intervals")
	}
	cfg.CPUPoll = time.Duration(doc.Telemetry.CPU) * time.Second
	cfg.MemPoll = cfg.CPUPoll
	cfg.NetPoll = cfg.CPUPoll
	return cfg, nil
}
