// Package server exposes the telemetry-agent HTTP API (Gin).
package server

import (
	"net/http"
	"time"

	"dt-ram/telemetry-agent/internal/collector"
	"dt-ram/telemetry-agent/internal/model"
	"dt-ram/telemetry-agent/internal/publisher"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	cpuGauge = prometheus.NewGauge(prometheus.GaugeOpts{Name: "telemetry_cpu_util", Help: "Last sampled CPU utilization 0..1"})
	memGauge = prometheus.NewGauge(prometheus.GaugeOpts{Name: "telemetry_mem_util", Help: "Last sampled memory utilization 0..1"})
)

func init() {
	prometheus.MustRegister(cpuGauge, memGauge)
}

// Deps wires collector + publisher + identity into HTTP handlers.
type Deps struct {
	NodeID    string
	Collector *collector.Collector
	Publisher publisher.Publisher
}

// Router builds the Gin engine.
func Router(d Deps) *gin.Engine {
	r := gin.New()
	r.Use(gin.Recovery())
	r.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok", "service": "telemetry-agent", "node_id": d.NodeID})
	})
	r.GET("/readyz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"ready": true})
	})
	r.GET("/metrics", gin.WrapH(promhttp.Handler()))
	r.GET("/collect", func(c *gin.Context) {
		m, err := d.Collector.Collect()
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		cpuGauge.Set(m.CPUUtil)
		memGauge.Set(m.MemoryUtil)
		ev := model.NewNodeMetricEvent(d.NodeID, m, time.Now().UTC())
		if err := d.Publisher.Publish(ev); err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, ev)
	})
	return r
}
