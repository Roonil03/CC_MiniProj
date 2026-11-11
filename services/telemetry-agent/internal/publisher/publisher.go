// Package publisher emits NODE_METRIC_UPDATED events to NATS JetStream.
// LogPublisher is the safe default (no network). NATSPublisher is used
// when TELEMETRY_PUBLISH_ENABLED=true and NATS is reachable.
package publisher

import (
	"encoding/json"
	"fmt"
	"log"
	"time"

	"dt-ram/telemetry-agent/internal/model"

	"github.com/nats-io/nats.go"
)

// Publisher is the event sink interface.
type Publisher interface {
	Publish(ev model.NodeMetricEvent) error
	Close() error
}

// LogPublisher logs events without network I/O (dev/test safe default).
type LogPublisher struct{}

func (LogPublisher) Publish(ev model.NodeMetricEvent) error {
	b, _ := json.Marshal(ev)
	log.Printf("telemetry event: %s", string(b))
	return nil
}

func (LogPublisher) Close() error { return nil }

// NATSPublisher publishes to NATS JetStream.
type NATSPublisher struct {
	nc      *nats.Conn
	js      nats.JetStreamContext
	subject string
}

// NewNATS connects to NATS and returns a JetStream publisher.
func NewNATS(url, subject string) (*NATSPublisher, error) {
	nc, err := nats.Connect(url)
	if err != nil {
		return nil, err
	}
	js, err := nc.JetStream()
	if err != nil {
		nc.Close()
		return nil, err
	}
	_, err = js.AddStream(&nats.StreamConfig{Name: "DT_TELEMETRY", Subjects: []string{subject}, Storage: nats.FileStorage, MaxAge: 24 * time.Hour, MaxMsgs: 100000})
	if err != nil {
		nc.Close()
		return nil, err
	}
	return &NATSPublisher{nc: nc, js: js, subject: subject}, nil
}

func (p *NATSPublisher) Publish(ev model.NodeMetricEvent) error {
	b, err := json.Marshal(ev)
	if err != nil {
		return err
	}
	// JetStream message IDs make a retry after an ambiguous publish response
	// idempotent within the stream's duplicate window.
	msg := &nats.Msg{Subject: p.subject, Data: b}
	msg.Header.Set(nats.MsgIdHdr, fmt.Sprintf("%s:%s", ev.NodeID, ev.Timestamp.UTC().Format(time.RFC3339Nano)))
	return publishWithRetry(func() error {
		_, publishErr := p.js.PublishMsg(msg)
		return publishErr
	})
}

func publishWithRetry(publish func() error) error {
	var err error
	for attempt := 0; attempt < 3; attempt++ {
		if err = publish(); err == nil {
			return nil
		}
		if attempt < 2 {
			time.Sleep(time.Duration(attempt+1) * 50 * time.Millisecond)
		}
	}
	return fmt.Errorf("JetStream publish failed after 3 attempts: %w", err)
}

func (p *NATSPublisher) Close() error {
	p.nc.Close()
	return nil
}
