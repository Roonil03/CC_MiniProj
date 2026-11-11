// Package audit keeps a bounded log of gated decisions with optional persistence.
package audit

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"

	"dt-ram/infrastructure-controller/internal/model"
)

const maxRecords = 10000

// Log is a concurrency-safe audit trail.
type Log struct {
	mu      sync.RWMutex
	records map[string]model.ActionRecord
	order   []string
	path    string
}

// New returns an empty audit log.
func New() *Log {
	return &Log{records: map[string]model.ActionRecord{}}
}

// NewPersistent restores a bounded local JSON snapshot before processing.
func NewPersistent(path string) (*Log, error) {
	l := New()
	l.path = path
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return l, nil
	}
	if err != nil {
		return nil, err
	}
	var rows []model.ActionRecord
	if err := json.Unmarshal(data, &rows); err != nil {
		return nil, err
	}
	if len(rows) > maxRecords {
		rows = rows[len(rows)-maxRecords:]
	}
	for _, row := range rows {
		if row.DecisionID == "" {
			continue
		}
		if _, exists := l.records[row.DecisionID]; !exists {
			l.order = append(l.order, row.DecisionID)
		}
		l.records[row.DecisionID] = row
	}
	return l, nil
}

// Append stores a record. Persistence failure leaves memory unchanged.
func (l *Log) Append(r model.ActionRecord) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	order := append([]string(nil), l.order...)
	records := make(map[string]model.ActionRecord, len(l.records)+1)
	for key, value := range l.records {
		records[key] = value
	}
	if _, ok := records[r.DecisionID]; !ok {
		order = append(order, r.DecisionID)
	}
	records[r.DecisionID] = r
	if len(order) > maxRecords {
		delete(records, order[0])
		order = order[1:]
	}
	if l.path != "" {
		rows := make([]model.ActionRecord, 0, len(order))
		for _, key := range order {
			rows = append(rows, records[key])
		}
		data, err := json.Marshal(rows)
		if err != nil {
			return err
		}
		if err := os.MkdirAll(filepath.Dir(l.path), 0700); err != nil {
			return err
		}
		temp := l.path + ".tmp"
		if err := os.WriteFile(temp, data, 0600); err != nil {
			return err
		}
		if err := os.Rename(temp, l.path); err != nil {
			_ = os.Remove(temp)
			return err
		}
	}
	l.records, l.order = records, order
	return nil
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
