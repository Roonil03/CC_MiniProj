// Package executor performs approved Kubernetes operations.
// LoggingExecutor is the non-destructive default (audit only).
// K8sExecutor uses client-go with least-privilege RBAC; it is selected
// automatically when a kubeconfig/cluster config is available, otherwise
// the controller stays in dry-run / logging mode and never mutates.
package executor

import (
	"context"
	"fmt"
	"log"

	"dt-ram/infrastructure-controller/internal/model"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

// Executor runs an approved action.
type Executor interface {
	Name() string
	Execute(ctx context.Context, namespace string, a model.Action) (string, error)
}

// LoggingExecutor records intent without touching the cluster.
type LoggingExecutor struct{}

func (LoggingExecutor) Name() string { return "logging (dry-run safe)" }

func (LoggingExecutor) Execute(_ context.Context, ns string, a model.Action) (string, error) {
	msg := fmt.Sprintf("dry-run %s service=%s ns=%s src=%s dst=%s", a.Type, a.Service, ns, a.Source, a.Destination)
	log.Println(msg)
	return msg, fmt.Errorf("logging executor cannot perform cluster mutations")
}

// K8sExecutor performs real scaling/placement via the K8s API.
type K8sExecutor struct {
	client kubernetes.Interface
}

// NewK8s builds an executor from kubeconfig path or in-cluster config.
// Empty kubeconfigPath falls back to in-cluster, then errors clearly.
func NewK8s(kubeconfigPath string) (*K8sExecutor, error) {
	var cfg *rest.Config
	var err error
	if kubeconfigPath != "" {
		cfg, err = clientcmd.BuildConfigFromFlags("", kubeconfigPath)
	} else {
		cfg, err = rest.InClusterConfig()
	}
	if err != nil {
		return nil, err
	}
	cs, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		return nil, err
	}
	return &K8sExecutor{client: cs}, nil
}

func (k *K8sExecutor) Name() string { return "kubernetes client-go" }

func (k *K8sExecutor) Execute(ctx context.Context, ns string, a model.Action) (string, error) {
	switch upper(a.Type) {
	case "SCALE":
		if a.Replicas == nil {
			return "", fmt.Errorf("replicas required for SCALE")
		}
		sc, err := k.client.AppsV1().Deployments(ns).GetScale(ctx, a.Service, metav1.GetOptions{})
		if err != nil {
			return "", fmt.Errorf("get scale %s: %w", a.Service, err)
		}
		sc.Spec.Replicas = int32(*a.Replicas)
		if _, err := k.client.AppsV1().Deployments(ns).UpdateScale(ctx, a.Service, sc, metav1.UpdateOptions{}); err != nil {
			return "", fmt.Errorf("update scale %s: %w", a.Service, err)
		}
		return fmt.Sprintf("scaled %s to %d replicas in ns %s", a.Service, *a.Replicas, ns), nil
	case "MIGRATE", "PLACE":
		return "", fmt.Errorf("placement execution is unavailable until rollout verification and rollback are implemented")
	case "NOOP":
		return "noop: no cluster operation", nil
	default:
		return "", fmt.Errorf("unsupported action type %q for executor", a.Type)
	}
}

func upper(s string) string {
	out := make([]byte, len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c >= 'a' && c <= 'z' {
			c -= 'a' - 'A'
		}
		out[i] = c
	}
	return string(out)
}
