// Package validator enforces the action schema gate:
// every command passes authentication -> schema validation -> policy
// validation -> safety validation -> Kubernetes operation (Design.md Sec 13).
package validator

import (
	"fmt"
	"strings"

	"dt-ram/infrastructure-controller/internal/model"
)

// ValidateAction rejects malformed or out-of-scope actions before safety checks.
func ValidateAction(a model.Action) error {
	switch strings.ToUpper(a.Type) {
	case "MIGRATE", "SCALE", "PLACE", "RESOURCE_ADJUST", "NOOP":
	default:
		return fmt.Errorf("unknown action type %q (want MIGRATE|SCALE|PLACE|RESOURCE_ADJUST|NOOP)", a.Type)
	}
	if strings.ToUpper(a.Type) == "NOOP" {
		return nil
	}
	if strings.TrimSpace(a.Service) == "" {
		return fmt.Errorf("service is required")
	}
	switch strings.ToUpper(a.Type) {
	case "MIGRATE", "PLACE":
		if strings.TrimSpace(a.Destination) == "" {
			return fmt.Errorf("destination is required for %s", a.Type)
		}
		if strings.EqualFold(a.Source, a.Destination) {
			return fmt.Errorf("source and destination must differ")
		}
	case "SCALE":
		if a.Replicas == nil || *a.Replicas < 0 {
			return fmt.Errorf("replicas must be >= 0 for SCALE")
		}
	}
	return nil
}
