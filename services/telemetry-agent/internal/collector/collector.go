// Package collector samples host CPU, memory and network utilization.
// It uses gopsutil with clamping so bursty CI runners never emit
// out-of-range values that would poison the Digital Twin.
package collector

import (
	"math"
	"time"

	"dt-ram/telemetry-agent/internal/model"

	"github.com/shirou/gopsutil/v3/cpu"
	"github.com/shirou/gopsutil/v3/mem"
	"github.com/shirou/gopsutil/v3/net"
)

// SampleFunc allows tests to inject deterministic samples.
type SampleFunc func() (model.NodeMetrics, error)

// Collector periodically samples host metrics.
type Collector struct {
	sample SampleFunc
	prevIn uint64
	prevOut uint64
	prevTs time.Time
	iface  string
}

// New returns a Collector backed by gopsutil.
func New() *Collector {
	c := &Collector{}
	c.sample = c.systemSample
	return c
}

// NewWithSample returns a Collector using a stub sampler (tests).
func NewWithSample(fn SampleFunc) *Collector {
	return &Collector{sample: fn}
}

// Collect returns one clamped utilization sample.
func (c *Collector) Collect() (model.NodeMetrics, error) {
	m, err := c.sample()
	if err != nil {
		return model.NodeMetrics{}, err
	}
	m.CPUUtil = clamp01(m.CPUUtil)
	m.MemoryUtil = clamp01(m.MemoryUtil)
	if m.NetworkInMbps < 0 {
		m.NetworkInMbps = 0
	}
	if m.NetworkOutMbps < 0 {
		m.NetworkOutMbps = 0
	}
	return m, nil
}

func (c *Collector) systemSample() (model.NodeMetrics, error) {
	var out model.NodeMetrics

	if pct, err := cpu.Percent(0, false); err == nil && len(pct) > 0 {
		out.CPUUtil = pct[0] / 100.0
	}
	if vm, err := mem.VirtualMemory(); err == nil && vm != nil {
		out.MemoryUtil = vm.UsedPercent / 100.0
	}
	// Best-effort network rate: bytes delta since last sample converted to Mbps.
	counters, err := net.IOCounters(false)
	if err == nil && len(counters) > 0 {
		now := time.Now()
		total := counters[0]
		if !c.prevTs.IsZero() {
			dt := now.Sub(c.prevTs).Seconds()
			if dt > 0 {
				out.NetworkInMbps = float64(total.BytesRecv-c.prevIn) * 8 / 1e6 / dt
				out.NetworkOutMbps = float64(total.BytesSent-c.prevOut) * 8 / 1e6 / dt
			}
		}
		c.prevIn, c.prevOut, c.prevTs = total.BytesRecv, total.BytesSent, now
	}
	return out, nil
}

func clamp01(v float64) float64 {
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return 0
	}
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}
