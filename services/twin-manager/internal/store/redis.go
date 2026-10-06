package store

import (
	"context"
	"dt-ram/twin-manager/internal/model"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"github.com/redis/go-redis/v9"
	"strings"
	"sync"
	"time"
)

// RedisStore is a single-process hot cache with durable write-through state.
// Redis atomically rejects timestamp regressions even across restarted writers.
type RedisStore struct {
	*MemoryStore
	client *redis.Client
	mu     sync.Mutex
}

const upsertScript = `
local previous = redis.call('HGET', KEYS[1], 'timestamp')
if previous and previous >= ARGV[1] then return 0 end
redis.call('HSET', KEYS[1], 'timestamp', ARGV[1], 'payload', ARGV[2])
return 1`

func NewRedis(addr string) (*RedisStore, error) {
	s := &RedisStore{MemoryStore: NewMemory(), client: redis.NewClient(&redis.Options{Addr: addr, MaxRetries: 0, DialTimeout: time.Second, ReadTimeout: time.Second, WriteTimeout: time.Second})}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := s.client.Ping(ctx).Err(); err != nil {
		s.Close()
		return nil, err
	}
	iter := s.client.Scan(ctx, 0, "dt-ram:twin:*", 100).Iterator()
	for iter.Next(ctx) {
		key := iter.Val()
		payload, err := s.client.HGet(ctx, key, "payload").Bytes()
		if err != nil {
			s.Close()
			return nil, err
		}
		if strings.HasPrefix(key, "dt-ram:twin:node:") {
			var n model.NodeState
			if err = json.Unmarshal(payload, &n); err == nil {
				err = s.MemoryStore.UpsertNode(n)
			}
		} else if strings.HasPrefix(key, "dt-ram:twin:workload:") {
			var w model.WorkloadState
			if err = json.Unmarshal(payload, &w); err == nil {
				err = s.MemoryStore.UpsertWorkload(w)
			}
		}
		if err != nil {
			s.Close()
			return nil, fmt.Errorf("restore %s: %w", key, err)
		}
	}
	if err := iter.Err(); err != nil {
		s.Close()
		return nil, err
	}
	return s, nil
}

func (s *RedisStore) Close() error { return s.client.Close() }

func (s *RedisStore) write(kind, id string, ts time.Time, value any) error {
	payload, err := json.Marshal(value)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	key := "dt-ram:twin:" + kind + ":" + base64.RawURLEncoding.EncodeToString([]byte(id))
	// Fixed-width seconds/nanoseconds compare lexicographically without float loss.
	timestamp := fmt.Sprintf("%020d.%09d", ts.Unix(), ts.Nanosecond())
	result, err := s.client.Eval(ctx, upsertScript, []string{key}, timestamp, payload).Int()
	if err != nil {
		return err
	}
	if result != 1 {
		return fmt.Errorf("update must be newer than persisted state")
	}
	return nil
}

func (s *RedisStore) UpsertNode(n model.NodeState) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if n.NodeID == "" || n.Timestamp.IsZero() {
		return fmt.Errorf("node_id and timestamp required")
	}
	if err := s.write("node", n.NodeID, n.Timestamp, n); err != nil {
		return err
	}
	return s.MemoryStore.UpsertNode(n)
}

func (s *RedisStore) UpsertWorkload(w model.WorkloadState) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if w.ServiceID == "" || w.Timestamp.IsZero() {
		return fmt.Errorf("service_id and timestamp required")
	}
	if err := s.write("workload", w.ServiceID+"/"+w.NodeID, w.Timestamp, w); err != nil {
		return err
	}
	return s.MemoryStore.UpsertWorkload(w)
}
