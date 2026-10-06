package server

import (
	"dt-ram/infrastructure-controller/internal/audit"
	"dt-ram/infrastructure-controller/internal/config"
	"dt-ram/infrastructure-controller/internal/executor"
	"dt-ram/infrastructure-controller/internal/safety"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHTTPDryRunAuditAndUnavailableDiscovery(t *testing.T) {
	cfg := config.Default()
	cfg.DryRun = true
	log := audit.New()
	router := Router(Deps{Config: cfg, Gate: safety.New(cfg), Executor: executor.LoggingExecutor{}, Audit: log})
	for _, path := range []string{"/infrastructure/nodes", "/infrastructure/pods"} {
		w := httptest.NewRecorder()
		router.ServeHTTP(w, httptest.NewRequest("GET", path, nil))
		if w.Code != 503 {
			t.Fatal(path, w.Code)
		}
	}
	body := `{"decision_id":"test","action":{"type":"NOOP"}}`
	for _, expected := range []int{200, 409} {
		w := httptest.NewRecorder()
		req := httptest.NewRequest("POST", "/actions/execute", strings.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		router.ServeHTTP(w, req)
		if w.Code != expected {
			t.Fatal(w.Code, w.Body.String())
		}
	}
	if rec, ok := log.Get("test"); !ok || rec.Executed || !rec.DryRun {
		t.Fatal(rec, ok)
	}
}
