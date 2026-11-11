// Package decision provides the shared HTTP/event pipeline. Live actuation is
// disabled until authoritative twin, counterfactual and safety contracts exist.
package decision

import (
	"context"
	"dt-ram/infrastructure-controller/internal/audit"
	"dt-ram/infrastructure-controller/internal/config"
	"dt-ram/infrastructure-controller/internal/model"
	"dt-ram/infrastructure-controller/internal/safety"
	"dt-ram/infrastructure-controller/internal/validator"
	"net/http"
	"sync"
	"time"
)

type Processor struct {
	mu     sync.Mutex
	Config config.Config
	Gate   *safety.Gate
	Audit  *audit.Log
}

func (p *Processor) Process(_ context.Context, req model.DecisionRequest) (model.ActionRecord, int) {
	p.mu.Lock()
	defer p.mu.Unlock()
	rec := model.ActionRecord{DecisionID: req.DecisionID, PolicyVersion: req.PolicyVersion,
		Action: req.Action, Predicted: req.Predicted, DTFidelity: req.DTFidelity,
		At: time.Now().UTC(), DryRun: p.Config.DryRun || req.DryRun}
	if req.DecisionID == "" {
		rec.Message = "decision_id is required"
		return rec, http.StatusUnprocessableEntity
	}
	if prior, ok := p.Audit.Get(req.DecisionID); ok {
		return prior, http.StatusConflict
	}
	status := http.StatusOK
	if err := validator.ValidateAction(req.Action); err != nil {
		rec.Verdict = model.SafetyVerdict{Reasons: []string{err.Error()}}
		status = http.StatusUnprocessableEntity
	} else {
		rec.Verdict = p.Gate.Evaluate(req)
		if !rec.Verdict.Approved {
			status = http.StatusUnprocessableEntity
		} else if rec.DryRun {
			rec.Message = "validated+approved (dry-run, no cluster mutation)"
		} else {
			rec.Verdict = model.SafetyVerdict{Reasons: []string{"live actuation disabled: authoritative twin freshness, counterfactual and safety-service integration are pending"}}
			status = http.StatusServiceUnavailable
		}
	}
	if err := p.Audit.Append(rec); err != nil {
		rec.Message = "audit store unavailable: " + err.Error()
		return rec, http.StatusServiceUnavailable
	}
	return rec, status
}
