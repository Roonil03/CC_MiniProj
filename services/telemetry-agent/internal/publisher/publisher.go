// Package publisher emits NODE_METRIC_UPDATED events to NATS JetStream.
// LogPublisher is the safe default (no network). NATSPublisher is used
// when TELEMETRY_PUBLISH_ENABLED=true and NATS is reachable.
package publisher

import (
	"encoding/json"
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
	_, err = p.js.Publish(p.subject, b)
	return err
}

func (p *NATSPublisher) Close() error {
	p.nc.Close()
	return nil
}
