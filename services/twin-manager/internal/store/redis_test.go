package store

import (
	"dt-ram/twin-manager/internal/model"
	"github.com/alicebob/miniredis/v2"
	"testing"
	"time"
)

func TestRedisRestartAndOrdering(t *testing.T) {
	server := miniredis.RunT(t)
	s, err := NewRedis(server.Addr())
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	node := model.NodeState{NodeID: "node", Timestamp: now, CPUCoreTotal: 4, CPUUsedCores: 2}
	if err := s.UpsertNode(node); err != nil {
		t.Fatal(err)
	}
	workload := model.WorkloadState{ServiceID: "app", NodeID: "node", Timestamp: now, Replicas: 2}
	if err := s.UpsertWorkload(workload); err != nil {
		t.Fatal(err)
	}
	s.Close()
	s, err = NewRedis(server.Addr())
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	if n, ok := s.GetNode("node"); !ok || n.CPUUsedCores != 2 {
		t.Fatal(n, ok)
	}
	if len(s.ListWorkloads()) != 1 {
		t.Fatal(s.ListWorkloads())
	}
	if err := s.UpsertNode(node); err == nil {
		t.Fatal("duplicate accepted")
	}
	node.Timestamp = now.Add(-time.Second)
	if err := s.UpsertNode(node); err == nil {
		t.Fatal("old state accepted")
	}
	node.Timestamp = now.Add(time.Second)
	node.CPUUsedCores = 3
	if err := s.UpsertNode(node); err != nil {
		t.Fatal(err)
	}
}

func TestRedisFailureDoesNotChangeHotState(t *testing.T) {
	server := miniredis.RunT(t)
	s, err := NewRedis(server.Addr())
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	n := model.NodeState{NodeID: "node", Timestamp: time.Now().UTC(), CPUUsedCores: 1}
	if err := s.UpsertNode(n); err != nil {
		t.Fatal(err)
	}
	server.Close()
	n.Timestamp = n.Timestamp.Add(time.Second)
	n.CPUUsedCores = 3
	if err := s.UpsertNode(n); err == nil {
		t.Fatal("unavailable Redis accepted")
	}
	if stored, _ := s.GetNode("node"); stored.CPUUsedCores != 1 {
		t.Fatal(stored)
	}
}
