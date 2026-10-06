package server_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"dt-ram/telemetry-agent/internal/collector"
	"dt-ram/telemetry-agent/internal/model"
	"dt-ram/telemetry-agent/internal/publisher"
	"dt-ram/telemetry-agent/internal/server"

	"github.com/stretchr/testify/require"
)

func testRouter() http.Handler {
	col := collector.NewWithSample(func() (model.NodeMetrics, error) {
		return model.NodeMetrics{CPUUtil: 0.5, MemoryUtil: 0.25, NetworkInMbps: 10, NetworkOutMbps: 5}, nil
	})
	return server.Router(server.Deps{NodeID: "edge-a1", Collector: col, Publisher: publisher.LogPublisher{}})
}

func TestHealthz(t *testing.T) {
	h := testRouter()
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	require.Equal(t, http.StatusOK, w.Code)
}

func TestCollectEndpointReturnsEventSchema(t *testing.T) {
	h := testRouter()
	req := httptest.NewRequest(http.MethodGet, "/collect", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	require.Equal(t, http.StatusOK, w.Code)
	var ev model.NodeMetricEvent
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &ev))
	require.Equal(t, "NODE_METRIC_UPDATED", ev.EventType)
	require.Equal(t, "edge-a1", ev.NodeID)
	require.False(t, ev.Timestamp.IsZero())
}
