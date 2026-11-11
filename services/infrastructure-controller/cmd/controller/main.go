// Command controller runs the DT-RAM infrastructure controller:
// the only service allowed to mutate Kubernetes.
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

	"dt-ram/infrastructure-controller/internal/audit"
	"dt-ram/infrastructure-controller/internal/config"
	"dt-ram/infrastructure-controller/internal/decision"
	"dt-ram/infrastructure-controller/internal/discovery"
	"dt-ram/infrastructure-controller/internal/executor"
	"dt-ram/infrastructure-controller/internal/model"
	"dt-ram/infrastructure-controller/internal/safety"
	"dt-ram/infrastructure-controller/internal/server"

	"github.com/nats-io/nats.go"
)

func main() {
	cfg, err := config.Load("configs/config.yaml")
	if err != nil {
		log.Fatalf("configuration: %v", err)
	}
	gate := safety.New(cfg)
	logStore := audit.New()
	if path := os.Getenv("DT_RAM_AUDIT_PATH"); path != "" {
		logStore, err = audit.NewPersistent(path)
		if err != nil {
			log.Fatalf("audit restore: %v", err)
		}
	}

	var ex executor.Executor = executor.LoggingExecutor{}
	if !cfg.DryRun {
		if kex, err := executor.NewK8s(cfg.Kubeconfig); err != nil {
			log.Printf("K8s client unavailable (%v); staying in logging mode", err)
		} else {
			ex = kex
		}
	} else {
		log.Println("CONTROLLER_DRY_RUN=true: cluster mutations disabled (safe default)")
	}

	processor := &decision.Processor{Config: cfg, Gate: gate, Audit: logStore}
	deps := server.Deps{Config: cfg, Gate: gate, Executor: ex, Audit: logStore, Processor: processor}
	if reader, err := discovery.New(cfg.Kubeconfig); err != nil {
		log.Printf("Kubernetes discovery unavailable: %v", err)
	} else {
		deps.Discovery = reader
	}

	// Best-effort NATS consumer for RESOURCE_DECISION events.
	if nc, err := nats.Connect(cfg.NATSURL); err != nil {
		log.Printf("NATS unavailable (%v); controller running in HTTP-only mode", err)
	} else {
		defer nc.Close()
		js, err := nc.JetStream()
		if err != nil {
			log.Fatalf("JetStream: %v", err)
		}
		if _, err = js.AddStream(&nats.StreamConfig{Name: "DT_DECISIONS", Subjects: []string{cfg.DecisionSubject}, Storage: nats.FileStorage, MaxAge: time.Hour, MaxMsgs: 10000}); err != nil {
			log.Fatalf("decision stream: %v", err)
		}
		_, err = js.Subscribe(cfg.DecisionSubject, func(m *nats.Msg) {
			var req model.DecisionRequest
			if err := json.Unmarshal(m.Data, &req); err != nil {
				log.Printf("bad decision event: %v", err)
				_ = m.Term()
				return
			}
			rec, status := processor.Process(context.Background(), req)
			log.Printf("decision %s status=%d result=%+v", req.DecisionID, status, rec)
			if status == http.StatusServiceUnavailable && strings.HasPrefix(rec.Message, "audit store unavailable:") {
				_ = m.Nak()
			} else {
				_ = m.Ack()
			}
		}, nats.Durable("infrastructure-controller"), nats.ManualAck(), nats.AckExplicit(),
			nats.MaxDeliver(3), nats.BindStream("DT_DECISIONS"))
		if err != nil {
			log.Printf("NATS subscribe failed: %v", err)
		}
	}

	r := server.Router(deps)
	srv := &http.Server{Addr: ":" + cfg.Port, Handler: r}
	go func() {
		log.Printf("infrastructure-controller listening on :%s executor=%s ns=%s", cfg.Port, ex.Name(), cfg.Namespace)
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
