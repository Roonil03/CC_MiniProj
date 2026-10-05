package collector_test

import (
	"errors"
	"testing"

	"dt-ram/telemetry-agent/internal/collector"
	"dt-ram/telemetry-agent/internal/model"

	"github.com/stretchr/testify/require"
)

func TestCollectClampsOutOfRange(t *testing.T) {
	c := collector.NewWithSample(func() (model.NodeMetrics, error) {
		return model.NodeMetrics{CPUUtil: 9.9, MemoryUtil: -2, NetworkInMbps: -5}, nil
	})
	m, err := c.Collect()
	require.NoError(t, err)
	require.Equal(t, 1.0, m.CPUUtil)
	require.Equal(t, 0.0, m.MemoryUtil)
	require.Equal(t, 0.0, m.NetworkInMbps)
}

func TestCollectPropagatesError(t *testing.T) {
	c := collector.NewWithSample(func() (model.NodeMetrics, error) {
		return model.NodeMetrics{}, errors.New("sensor boom")
	})
	_, err := c.Collect()
	require.Error(t, err)
}
