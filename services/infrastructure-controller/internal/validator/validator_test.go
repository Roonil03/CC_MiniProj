package validator_test

import (
	"testing"

	"dt-ram/infrastructure-controller/internal/model"
	"dt-ram/infrastructure-controller/internal/validator"

	"github.com/stretchr/testify/require"
)

func TestRejectUnknownType(t *testing.T) {
	require.Error(t, validator.ValidateAction(model.Action{Type: "DELETE_CLUSTER", Service: "x"}))
}

func TestRejectSameSourceDestination(t *testing.T) {
	require.Error(t, validator.ValidateAction(model.Action{Type: "MIGRATE", Service: "p", Source: "a", Destination: "a"}))
}

func TestAcceptNoop(t *testing.T) {
	require.NoError(t, validator.ValidateAction(model.Action{Type: "NOOP"}))
}
