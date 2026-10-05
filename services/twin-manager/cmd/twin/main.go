// Command twin runs the DT-RAM twin-manager: synchronized virtual state,
// fidelity scoring and the HTTP/NATS sync surface (Design.md Sections 15-18).
package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"dt-ram/twin-manager/internal/config"
	"dt-ram/twin-manager/internal/model"
	"dt-ram/twin-manager/internal/server"
	twinsync "dt-ram/twin-manager/internal/sync"
	"dt-ram/twin-manager/internal/store"

	"github.com/nats-io/nats.go"
)

func main() {
	cfg := config.Default()
	st := store.NewMemory()
	engine := twinsync.New(st, cfg.StaleAfter)

	// Best-effort NATS subscriber for NODE_METRIC_UPDATED (optional in dev).
	if nc, err := nats.Connect(cfg.NATSURL); err != nil {
		log.Printf("NATS unavailable (%v); twin-manager running in HTTP-only mode", err)
	} else {
		defer nc.Close()
		_, err = nc.Subscribe(cfg.SubscribeSubject, func(m *nats.Msg) {
			var ev struct {
				NodeID    string    `json:"node_id"`
				Timestamp time.Time `json:"timestamp"`
				Metrics   struct {
					CPU     float64 `json:"cpu"`
					Memory  float64 `json:"memory"`
					NetIn   float64 `json:"network_in"`
					NetOut  float64 `json:"network_out"`
				} `json:"metrics"`
			}
			if err := json.Unmarshal(m.Data, &ev); err != nil {
				log.Printf("bad telemetry event: %v", err)
				return
			}
			if _, err := engine.ApplyTelemetry(model.TelemetryIngest{
				NodeID: ev.NodeID, CPUUtil: ev.Metrics.CPU, MemoryUtil: ev.Metrics.Memory,
				NetworkInMbps: ev.Metrics.NetIn, NetworkOutMbps: ev.Metrics.NetOut, Timestamp: ev.Timestamp,
			}); err != nil {
				log.Printf("sync reject: %v", err)
			}
		})
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
