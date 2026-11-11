package audit_test

import (
	"path/filepath"
	"testing"

	"dt-ram/infrastructure-controller/internal/audit"
	"dt-ram/infrastructure-controller/internal/model"
)

func TestPersistentAuditRestoresDecisionInputs(t *testing.T) {
	path := filepath.Join(t.TempDir(), "audit.json")
	log, err := audit.NewPersistent(path)
	if err != nil {
		t.Fatal(err)
	}
	record := model.ActionRecord{DecisionID: "decision-1", PolicyVersion: "policy-v1",
		Action: model.Action{Type: "NOOP"}, DTFidelity: 0.97}
	if err := log.Append(record); err != nil {
		t.Fatal(err)
	}
	restored, err := audit.NewPersistent(path)
	if err != nil {
		t.Fatal(err)
	}
	got, ok := restored.Get("decision-1")
	if !ok || got.PolicyVersion != "policy-v1" || got.DTFidelity != 0.97 {
		t.Fatalf("missing restored decision inputs: %+v", got)
	}
	if err := restored.Append(model.ActionRecord{DecisionID: "decision-2"}); err != nil {
		t.Fatal(err)
	}
}
