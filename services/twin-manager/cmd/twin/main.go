// Command twin runs the DT-RAM twin-manager: synchronized virtual state,
// fidelity scoring and the HTTP/NATS sync surface.
package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"dt-ram/twin-manager/internal/config"
	"dt-ram/twin-manager/internal/model"
	"dt-ram/twin-manager/internal/server"
	"dt-ram/twin-manager/internal/store"
	twinsync "dt-ram/twin-manager/internal/sync"

	"github.com/nats-io/nats.go"
)

func main() {
	cfg, err := config.Load("configs/config.yaml")
	if err != nil {
		log.Fatalf("configuration: %v", err)
	}
	var st store.Store = store.NewMemory()
	if cfg.RedisAddr != "" {
		persistent, err := store.NewRedis(cfg.RedisAddr)
		if err != nil {
			log.Fatalf("configured Redis store unavailable: %v", err)
		}
		defer persistent.Close()
		st = persistent
	}
	engine := twinsync.New(st, cfg.StaleAfter)

	// Best-effort NATS subscriber for NODE_METRIC_UPDATED (optional in dev).
	if nc, err := nats.Connect(cfg.NATSURL); err != nil {
		log.Printf("NATS unavailable (%v); twin-manager running in HTTP-only mode", err)
	} else {
		defer nc.Close()
		js, err := nc.JetStream()
		if err != nil {
			log.Fatalf("JetStream: %v", err)
		}
		if _, err = js.AddStream(&nats.StreamConfig{Name: "DT_TELEMETRY", Subjects: []string{cfg.SubscribeSubject}, Storage: nats.FileStorage, MaxAge: 24 * time.Hour, MaxMsgs: 100000}); err != nil {
			log.Fatalf("telemetry stream: %v", err)
		}
		// Ephemeral consumer replays retained state on restart because the store is in memory.
		_, err = js.Subscribe(cfg.SubscribeSubject, func(m *nats.Msg) {
			var ev struct {
				EventType string    `json:"event_type"`
				NodeID    string    `json:"node_id"`
				Timestamp time.Time `json:"timestamp"`
				Metrics   struct {
					CPUTotal    *float64 `json:"cpu_total"`
					MemoryTotal *float64 `json:"memory_total_mb"`
					CPU         *float64 `json:"cpu"`
					Memory      *float64 `json:"memory"`
					NetIn       *float64 `json:"network_in"`
					NetOut      *float64 `json:"network_out"`
				} `json:"metrics"`
			}
			if err := json.Unmarshal(m.Data, &ev); err != nil {
				log.Printf("bad telemetry event: %v", err)
				_ = m.Term()
				return
			}
			if ev.EventType != "NODE_METRIC_UPDATED" || ev.NodeID == "" || ev.Timestamp.IsZero() {
				_ = m.Term()
				return
			}
			if _, err := engine.ApplyTelemetry(model.TelemetryIngest{
				NodeID: ev.NodeID, CPUUtil: ev.Metrics.CPU, MemoryUtil: ev.Metrics.Memory,
				CPUTotalCores: ev.Metrics.CPUTotal, MemoryTotalMB: ev.Metrics.MemoryTotal,
				NetworkInMbps: ev.Metrics.NetIn, NetworkOutMbps: ev.Metrics.NetOut, Timestamp: ev.Timestamp,
			}); err != nil {
				log.Printf("sync reject: %v", err)
				if strings.Contains(err.Error(), "newer than stored state") || strings.Contains(err.Error(), "must be newer") || strings.Contains(err.Error(), "newer than persisted state") {
					// Replay and out-of-order samples are permanent; terminate to avoid
					// retry loops while preserving the newer twin state.
					_ = m.Term()
				} else if strings.Contains(err.Error(), "required") || strings.Contains(err.Error(), "must be in") || strings.Contains(err.Error(), "finite and nonnegative") || strings.Contains(err.Error(), "future") {
					_ = m.Term()
				} else {
					// Store/backend failures are retryable; do not drop telemetry.
					_ = m.NakWithDelay(time.Second)
				}
				return
			}
			_ = m.Ack()
		}, nats.ManualAck(), nats.AckExplicit(), nats.DeliverAll(), nats.BindStream("DT_TELEMETRY"))
		if err != nil {
			log.Printf("NATS subscribe failed: %v", err)
		} else {
			log.Printf("subscribed to NATS subject %s", cfg.SubscribeSubject)
		}
	}

	r := server.Router(server.Deps{Store: st, Engine: engine})
	srv := &http.Server{Addr: ":" + cfg.Port, Handler: r}
	go func() {
		log.Printf("twin-manager listening on :%s (redis %s)", cfg.Port, cfg.RedisAddr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("listen: %v", err)
		}
	}()
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(ctx)
}
