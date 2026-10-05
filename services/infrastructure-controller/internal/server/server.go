// Package server exposes the infrastructure-controller HTTP API (Gin).
//
// Pipeline per decision: schema validation -> safety gate -> executor.
// Rejected actions return 422 with reasons and are audit-logged.
package server

import (
	"context"
	"net/http"
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
	Config   config.Config
	Gate     *safety.Gate
	Executor executor.Executor
	Audit    *audit.Log
}

// Router builds the Gin engine.
func Router(d Deps) *gin.Engine {
	r := gin.New()
	r.Use(gin.Recovery())
	r.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok", "service": "infrastructure-controller", "executor": d.Executor.Name()})
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
		if err := validator.ValidateAction(req.Action); err != nil {
			rec := model.ActionRecord{DecisionID: req.DecisionID, Action: req.Action, Verdict: model.SafetyVerdict{Reasons: []string{err.Error()}}, At: time.Now().UTC()}
			d.Audit.Append(rec)
			c.JSON(http.StatusUnprocessableEntity, rec)
			return
		}
		v := d.Gate.Evaluate(req)
		rec := model.ActionRecord{DecisionID: req.DecisionID, Action: req.Action, Verdict: v, At: time.Now().UTC(), DryRun: req.DryRun || d.Config.DryRun}
		if !v.Approved {
			d.Audit.Append(rec)
			c.JSON(http.StatusUnprocessableEntity, rec)
			return
		}
		if rec.DryRun {
			rec.Message = "validated+approved (dry-run, no cluster mutation)"
			d.Audit.Append(rec)
			c.JSON(http.StatusOK, rec)
			return
		}
		ctx, cancel := context.WithTimeout(c.Request.Context(), 20*time.Second)
		defer cancel()
		msg, err := d.Executor.Execute(ctx, d.Config.Namespace, req.Action)
		if err != nil {
			rec.Message = err.Error()
			d.Audit.Append(rec)
			c.JSON(http.StatusBadGateway, rec)
			return
		}
		rec.Executed = true
		rec.Message = msg
		if upper(req.Action.Type) == "MIGRATE" {
			d.Gate.RecordMigration(req.Action.Source)
		}
		d.Audit.Append(rec)
		c.JSON(http.StatusOK, rec)
	})
	return r
}

func upper(s string) string {
	b := []byte(s)
	for i, ch := range b {
		if ch >= 'a' && ch <= 'z' {
			b[i] = ch - ('a' - 'A')
		}
	}
	return string(b)
}
