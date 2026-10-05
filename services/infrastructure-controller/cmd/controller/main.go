// Command controller runs the DT-RAM infrastructure controller:
// the only service allowed to mutate Kubernetes (Design.md Sections 13, 66).
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

	"dt-ram/infrastructure-controller/internal/audit"
	"dt-ram/infrastructure-controller/internal/config"
	"dt-ram/infrastructure-controller/internal/executor"
	"dt-ram/infrastructure-controller/internal/model"
	"dt-ram/infrastructure-controller/internal/safety"
	"dt-ram/infrastructure-controller/internal/server"
	"dt-ram/infrastructure-controller/internal/validator"

	"github.com/nats-io/nats.go"
)

func main() {
	cfg := config.Default()
	gate := safety.New(cfg)
	logStore := audit.New()

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

	deps := server.Deps{Config: cfg, Gate: gate, Executor: ex, Audit: logStore}

	// Best-effort NATS consumer for RESOURCE_DECISION events (Design Sec 54).
	if nc, err := nats.Connect(cfg.NATSURL); err != nil {
		log.Printf("NATS unavailable (%v); controller running in HTTP-only mode", err)
	} else {
		defer nc.Close()
		_, err = nc.Subscribe(cfg.DecisionSubject, func(m *nats.Msg) {
			var req model.DecisionRequest
			if err := json.Unmarshal(m.Data, &req); err != nil {
				log.Printf("bad decision event: %v", err)
				return
			}
			if err := validator.ValidateAction(req.Action); err != nil {
				log.Printf("decision %s schema reject: %v", req.DecisionID, err)
				return
			}
			v := gate.Evaluate(req)
			if !v.Approved {
				log.Printf("decision %s safety reject: %v", req.DecisionID, v.Reasons)
				logStore.Append(model.ActionRecord{DecisionID: req.DecisionID, Action: req.Action, Verdict: v, At: time.Now().UTC(), DryRun: true})
				return
			}
			log.Printf("decision %s approved: %v", req.DecisionID, v.Reasons)
		})
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
