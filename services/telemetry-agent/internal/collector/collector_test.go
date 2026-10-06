package collector_test

import (
	"errors"
	"math"
	"sync"
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

func TestConcurrentSamples(t *testing.T) {
	count := 0
	c := collector.NewWithSample(func() (model.NodeMetrics, error) { count++; return model.NodeMetrics{}, nil })
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() { defer wg.Done(); c.Collect() }()
	}
	wg.Wait()
	require.Equal(t, 20, count)
}

func TestRejectNonfiniteNetwork(t *testing.T) {
	c := collector.NewWithSample(func() (model.NodeMetrics, error) { return model.NodeMetrics{NetworkInMbps: math.NaN()}, nil })
	_, err := c.Collect()
	require.Error(t, err)
}

func TestCollectPropagatesError(t *testing.T) {
	c := collector.NewWithSample(func() (model.NodeMetrics, error) {
		return model.NodeMetrics{}, errors.New("sensor boom")
	})
	_, err := c.Collect()
	require.Error(t, err)
}
