// Package server exposes the twin-manager HTTP API (Gin).
package server

import (
	"fmt"
	"net/http"

	"dt-ram/twin-manager/internal/fidelity"
	"dt-ram/twin-manager/internal/model"
	"dt-ram/twin-manager/internal/store"
	twinsync "dt-ram/twin-manager/internal/sync"

	"github.com/gin-gonic/gin"
)

// Deps wires store + sync engine into handlers.
type Deps struct {
	Store  store.Store
	Engine *twinsync.SyncEngine
}

// Router builds the Gin engine.
func Router(d Deps) *gin.Engine {
	r := gin.New()
	r.Use(gin.Recovery())
	r.GET("/metrics", func(c *gin.Context) {
		nodes := d.Engine.Nodes()
		stale := 0
		for _, node := range nodes {
			if node.Stale {
				stale++
			}
		}
		c.Data(http.StatusOK, "text/plain; version=0.0.4", []byte(fmt.Sprintf("# TYPE twin_nodes gauge\ntwin_nodes %d\n# TYPE twin_stale_nodes gauge\ntwin_stale_nodes %d\n", len(nodes), stale)))
	})
	r.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok", "service": "twin-manager"})
	})
	r.GET("/twin/state", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"nodes": d.Engine.Nodes(), "workloads": d.Store.ListWorkloads()})
	})
	r.GET("/twin/state/:node_id", func(c *gin.Context) {
		n, ok := d.Store.GetNode(c.Param("node_id"))
		if !ok {
			c.JSON(http.StatusNotFound, gin.H{"error": "node not found"})
			return
		}
		c.JSON(http.StatusOK, d.Engine.Refresh(n))
	})
	r.POST("/twin/update", func(c *gin.Context) {
		var in model.TelemetryIngest
		if err := c.ShouldBindJSON(&in); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		n, err := d.Engine.ApplyTelemetry(in)
		if err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, n)
	})
	r.GET("/twin/fidelity", func(c *gin.Context) {
		nodes := d.Engine.Nodes()
		reports := make([]model.FidelityReport, 0, len(nodes))
		for _, n := range nodes {
			reports = append(reports, fidelity.Report(n))
		}
		c.JSON(http.StatusOK, gin.H{"reports": reports})
	})
	return r
}
