package publisher

import (
	"dt-ram/telemetry-agent/internal/model"
	"errors"
	"github.com/nats-io/nats.go"
	"os"
	"testing"
	"time"
)

func TestPublishWithRetryRetriesThenSucceeds(t *testing.T) {
	calls := 0
	err := publishWithRetry(func() error {
		calls++
		if calls < 3 {
			return errors.New("temporary acknowledgement failure")
		}
		return nil
	})
	if err != nil || calls != 3 {
		t.Fatalf("retry result calls=%d err=%v", calls, err)
	}
}

func TestPublishWithRetryReturnsFinalFailure(t *testing.T) {
	calls := 0
	err := publishWithRetry(func() error { calls++; return errors.New("offline") })
	if err == nil || calls != 3 {
		t.Fatalf("expected bounded failure calls=%d err=%v", calls, err)
	}
}

// Run against an isolated JetStream server with NATS_TEST_URL set.
func TestJetStreamPublishAndReplay(t *testing.T) {
	url := os.Getenv("NATS_TEST_URL")
	if url == "" {
		t.Skip("NATS_TEST_URL required for JetStream integration")
	}
	pub, err := NewNATS(url, "dt.telemetry.node_metric")
	if err != nil {
		t.Fatal(err)
	}
	defer pub.Close()
	ev := model.NewNodeMetricEvent("integration-node", model.NodeMetrics{CPUUtil: .4, CPUTotalCores: 4, MemoryTotalMB: 2048}, time.Now())
	if err := pub.Publish(ev); err != nil {
		t.Fatal(err)
	}
	nc, err := nats.Connect(url)
	if err != nil {
		t.Fatal(err)
	}
	defer nc.Close()
	js, err := nc.JetStream()
	if err != nil {
		t.Fatal(err)
	}
	sub, err := js.SubscribeSync("dt.telemetry.node_metric", nats.DeliverAll(), nats.ManualAck(), nats.BindStream("DT_TELEMETRY"))
	if err != nil {
		t.Fatal(err)
	}
	defer sub.Unsubscribe()
	msg, err := sub.NextMsg(5 * time.Second)
	if err != nil {
		t.Fatal("retained telemetry unavailable", err)
	}
	if err := msg.AckSync(); err != nil {
		t.Fatal(err)
	}
	info, err := js.StreamInfo("DT_TELEMETRY")
	if err != nil || info.State.Msgs == 0 {
		t.Fatal(info, err)
	}
}
