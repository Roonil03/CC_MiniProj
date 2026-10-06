// Package store keeps synchronized twin state.
// MemoryStore is the hermetic default used in tests and local dev.
// RedisStore adds opt-in write-through persistence. Postgres is not implemented.
package store

import (
	"fmt"
	"sync"
	"time"

	"dt-ram/twin-manager/internal/model"
)

// Store is the twin state interface.
type Store interface {
	UpsertNode(n model.NodeState) error
	GetNode(id string) (model.NodeState, bool)
	ListNodes() []model.NodeState
	UpsertWorkload(w model.WorkloadState) error
	ListWorkloads() []model.WorkloadState
}

// MemoryStore is a concurrency-safe in-memory twin store.
type MemoryStore struct {
	mu        sync.RWMutex
	nodes     map[string]model.NodeState
	workloads map[string]model.WorkloadState
}

// NewMemory returns an empty store.
func NewMemory() *MemoryStore {
	return &MemoryStore{nodes: map[string]model.NodeState{}, workloads: map[string]model.WorkloadState{}}
}

func (s *MemoryStore) UpsertNode(n model.NodeState) error {
	if n.NodeID == "" {
		return fmt.Errorf("node_id is required")
	}
	if n.Timestamp.IsZero() {
		n.Timestamp = time.Now().UTC()
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if prev, ok := s.nodes[n.NodeID]; ok && !n.Timestamp.After(prev.Timestamp) {
		return fmt.Errorf("node update must be newer than stored state")
	}
	s.nodes[n.NodeID] = n
	return nil
}

func (s *MemoryStore) GetNode(id string) (model.NodeState, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	n, ok := s.nodes[id]
	return n, ok
}

func (s *MemoryStore) ListNodes() []model.NodeState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]model.NodeState, 0, len(s.nodes))
	for _, n := range s.nodes {
		out = append(out, n)
	}
	return out
}

func (s *MemoryStore) UpsertWorkload(w model.WorkloadState) error {
	if w.ServiceID == "" {
		return fmt.Errorf("service_id is required")
	}
	if w.Timestamp.IsZero() {
		w.Timestamp = time.Now().UTC()
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	key := w.ServiceID + "/" + w.NodeID
	if prev, ok := s.workloads[key]; ok && !w.Timestamp.After(prev.Timestamp) {
		return fmt.Errorf("workload update must be newer than stored state")
	}
	s.workloads[key] = w
	return nil
}

func (s *MemoryStore) ListWorkloads() []model.WorkloadState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]model.WorkloadState, 0, len(s.workloads))
	for _, w := range s.workloads {
		out = append(out, w)
	}
	return out
}
