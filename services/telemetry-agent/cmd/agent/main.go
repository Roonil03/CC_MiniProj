// Command agent runs the DT-RAM telemetry agent: collects host metrics
// and publishes NODE_METRIC_UPDATED events (Design.md Section 53).
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"dt-ram/telemetry-agent/internal/collector"
	"dt-ram/telemetry-agent/internal/config"
	"dt-ram/telemetry-agent/internal/model"
	"dt-ram/telemetry-agent/internal/publisher"
	"dt-ram/telemetry-agent/internal/server"
)

func main() {
	cfg := config.Default()
	col := collector.New()

	var pub publisher.Publisher = publisher.LogPublisher{}
	if cfg.PublishEnabled {
		np, err := publisher.NewNATS(cfg.NATSURL, cfg.PublishSubject)
		if err != nil {
			log.Fatalf("telemetry publishing enabled but JetStream unavailable: %v", err)
		} else {
			pub = np
			defer np.Close()
		}
	}

	r := server.Router(server.Deps{NodeID: cfg.NodeID, Collector: col, Publisher: pub})
	srv := &http.Server{Addr: ":" + cfg.Port, Handler: r}

	go func() {
		log.Printf("telemetry-agent node=%s listening on :%s", cfg.NodeID, cfg.Port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("listen: %v", err)
		}
	}()

	// Background sampler at CPU poll interval (Design.md Section 17: 1s).
	ticker := time.NewTicker(cfg.CPUPoll)
	defer ticker.Stop()
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	for {
		select {
		case <-ticker.C:
			m, err := col.Collect()
			if err != nil {
				log.Printf("collect error: %v", err)
				continue
			}
			ev := model.NewNodeMetricEvent(cfg.NodeID, m, time.Now().UTC())
			server.Observe(m)
			if err := pub.Publish(ev); err != nil {
				log.Printf("publish error: %v", err)
			}
		case <-stop:
			log.Println("shutting down telemetry-agent")
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = srv.Shutdown(ctx)
			return
		}
	}
}
