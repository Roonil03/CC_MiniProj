// Package server exposes the infrastructure-controller HTTP API (Gin).
//
// Decisions are validated and audited in dry-run mode. Live execution returns
// 503 until the authoritative twin/counterfactual/safety contract is implemented.
package server

import (
	"context"
	"dt-ram/infrastructure-controller/internal/decision"
	"dt-ram/infrastructure-controller/internal/discovery"
	"fmt"
	"net/http"
	"os"
	"time"

	"dt-ram/infrastructure-controller/internal/audit"
	"dt-ram/infrastructure-controller/internal/config"
	"dt-ram/infrastructure-controller/internal/executor"
	"dt-ram/infrastructure-controller/internal/model"
	"dt-ram/infrastructure-controller/internal/safety"
	"dt-ram/infrastructure-controller/internal/validator"

	"github.com/gin-gonic/gin"
)

// Deps wires config, safety gate, executor and audit log.
type Deps struct {
	Config    config.Config
	Gate      *safety.Gate
	Executor  executor.Executor
	Audit     *audit.Log
	Processor *decision.Processor
	Discovery discovery.Reader
}

// Router builds the Gin engine.
func Router(d Deps) *gin.Engine {
	if d.Processor == nil {
		d.Processor = &decision.Processor{Config: d.Config, Gate: d.Gate, Audit: d.Audit}
	}
	r := gin.New()
	r.Use(gin.Recovery())
	serviceToken := os.Getenv("DT_RAM_SERVICE_TOKEN")
	r.Use(func(c *gin.Context) {
		if serviceToken != "" && c.Request.URL.Path != "/healthz" && c.Request.URL.Path != "/readyz" && c.Request.URL.Path != "/metrics" && c.GetHeader("x-service-token") != serviceToken {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
			return
		}
		c.Next()
	})
	r.GET("/metrics", func(c *gin.Context) {
		records := d.Audit.List()
		rejected := 0
		for _, record := range records {
			if !record.Verdict.Approved {
				rejected++
			}
		}
		c.Data(http.StatusOK, "text/plain; version=0.0.4", []byte(fmt.Sprintf("# TYPE controller_audit_records gauge\ncontroller_audit_records %d\n# TYPE controller_rejected_records gauge\ncontroller_rejected_records %d\n", len(records), rejected)))
	})
	r.GET("/infrastructure/nodes", func(c *gin.Context) {
		if d.Discovery == nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Kubernetes discovery unavailable"})
			return
		}
		ctx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
		defer cancel()
		nodes, err := d.Discovery.Nodes(ctx)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, nodes)
	})
	r.GET("/infrastructure/pods", func(c *gin.Context) {
		if d.Discovery == nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Kubernetes discovery unavailable"})
			return
		}
		ctx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
		defer cancel()
		pods, err := d.Discovery.Pods(ctx, d.Config.Namespace)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, pods)
	})
	r.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok", "service": "infrastructure-controller", "executor": d.Executor.Name()})
	})
	r.GET("/readyz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok", "service": "infrastructure-controller"})
	})
	r.GET("/actions", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"actions": d.Audit.List()})
	})
	r.GET("/actions/:id", func(c *gin.Context) {
		rec, ok := d.Audit.Get(c.Param("id"))
		if !ok {
			c.JSON(http.StatusNotFound, gin.H{"error": "decision not found"})
			return
		}
		c.JSON(http.StatusOK, rec)
	})
	r.POST("/actions/validate", func(c *gin.Context) {
		var req model.DecisionRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		if err := validator.ValidateAction(req.Action); err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"approved": false, "reasons": []string{err.Error()}})
			return
		}
		v := d.Gate.Evaluate(req)
		c.JSON(http.StatusOK, gin.H{"approved": v.Approved, "reasons": v.Reasons})
	})
	r.POST("/actions/execute", func(c *gin.Context) {
		var req model.DecisionRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		rec, status := d.Processor.Process(c.Request.Context(), req)
		c.JSON(status, rec)
	})
	return r
}
