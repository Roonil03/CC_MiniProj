// Package audit keeps an in-memory log of gated decisions.
package audit

import (
	"sync"

	"dt-ram/infrastructure-controller/internal/model"
)

// Log is a concurrency-safe audit trail.
type Log struct {
	mu      sync.RWMutex
	records map[string]model.ActionRecord
	order   []string
}

// New returns an empty audit log.
func New() *Log {
	return &Log{records: map[string]model.ActionRecord{}}
}

// Append stores a record.
func (l *Log) Append(r model.ActionRecord) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if _, ok := l.records[r.DecisionID]; !ok {
		l.order = append(l.order, r.DecisionID)
	}
	l.records[r.DecisionID] = r
}

// Get fetches one record.
func (l *Log) Get(id string) (model.ActionRecord, bool) {
	l.mu.RLock()
	defer l.mu.RUnlock()
	r, ok := l.records[id]
	return r, ok
}

// List returns records in insertion order.
func (l *Log) List() []model.ActionRecord {
	l.mu.RLock()
	defer l.mu.RUnlock()
	out := make([]model.ActionRecord, 0, len(l.order))
	for _, id := range l.order {
		out = append(out, l.records[id])
	}
	return out
}
