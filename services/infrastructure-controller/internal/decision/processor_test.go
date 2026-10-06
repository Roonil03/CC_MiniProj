package decision

import (
	"context"
	"dt-ram/infrastructure-controller/internal/audit"
	"dt-ram/infrastructure-controller/internal/config"
	"dt-ram/infrastructure-controller/internal/model"
	"dt-ram/infrastructure-controller/internal/safety"
	"net/http"
	"sync"
	"testing"
)

func TestAuditDryRunAndLiveBlock(t *testing.T) {
	cfg := config.Default()
	cfg.DryRun = false
	p := &Processor{Config: cfg, Gate: safety.New(cfg), Audit: audit.New()}
	req := model.DecisionRequest{DecisionID: "one", Action: model.Action{Type: "NOOP"}, DryRun: true}
	rec, status := p.Process(context.Background(), req)
	if status != http.StatusOK || rec.Executed || !rec.DryRun {
		t.Fatal(rec, status)
	}
	req.DecisionID = "two"
	req.DryRun = false
	rec, status = p.Process(context.Background(), req)
	if status != http.StatusServiceUnavailable || rec.Verdict.Approved || rec.Executed {
		t.Fatal(rec, status)
	}
	req.DecisionID = "three"
	req.Action.Type = "BAD"
	_, status = p.Process(context.Background(), req)
	if status != http.StatusUnprocessableEntity || len(p.Audit.List()) != 3 {
		t.Fatal(status, p.Audit.List())
	}
	req.DecisionID = ""
	_, status = p.Process(context.Background(), req)
	if status != http.StatusUnprocessableEntity {
		t.Fatal(status)
	}
}

func TestConcurrentDuplicate(t *testing.T) {
	cfg := config.Default()
	p := &Processor{Config: cfg, Gate: safety.New(cfg), Audit: audit.New()}
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			p.Process(context.Background(), model.DecisionRequest{DecisionID: "same", Action: model.Action{Type: "NOOP"}})
		}()
	}
	wg.Wait()
	if len(p.Audit.List()) != 1 {
		t.Fatal(p.Audit.List())
	}
	_, status := p.Process(context.Background(), model.DecisionRequest{DecisionID: "same", Action: model.Action{Type: "SCALE"}})
	if status != http.StatusConflict {
		t.Fatal(status)
	}
}
