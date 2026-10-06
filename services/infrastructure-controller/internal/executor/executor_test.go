package executor

import (
	"context"
	"dt-ram/infrastructure-controller/internal/model"
	autoscalingv1 "k8s.io/api/autoscaling/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/kubernetes/fake"
	ktesting "k8s.io/client-go/testing"
	"testing"
)

func TestScaleCommand(t *testing.T) {
	client := fake.NewSimpleClientset()
	client.PrependReactor("get", "deployments", func(a ktesting.Action) (bool, runtime.Object, error) {
		if a.GetSubresource() != "scale" {
			t.Fatal(a)
		}
		return true, &autoscalingv1.Scale{ObjectMeta: metav1.ObjectMeta{Name: "app", Namespace: "dt-ram"}, Spec: autoscalingv1.ScaleSpec{Replicas: 1}}, nil
	})
	client.PrependReactor("update", "deployments", func(a ktesting.Action) (bool, runtime.Object, error) {
		scale := a.(ktesting.UpdateAction).GetObject().(*autoscalingv1.Scale)
		if a.GetNamespace() != "dt-ram" || a.GetSubresource() != "scale" || scale.Spec.Replicas != 3 {
			t.Fatal(a, scale)
		}
		return true, scale, nil
	})
	replicas := 3
	ex := &K8sExecutor{client: client}
	if _, err := ex.Execute(context.Background(), "dt-ram", model.Action{Type: "SCALE", Service: "app", Replicas: &replicas}); err != nil {
		t.Fatal(err)
	}
	if len(client.Actions()) != 2 {
		t.Fatal(client.Actions())
	}
}

func TestUnsupportedPlacementDoesNotMutate(t *testing.T) {
	client := fake.NewSimpleClientset()
	ex := &K8sExecutor{client: client}
	for _, kind := range []string{"MIGRATE", "PLACE", "RESOURCE_ADJUST"} {
		if _, err := ex.Execute(context.Background(), "dt-ram", model.Action{Type: kind, Service: "app", Destination: "node"}); err == nil {
			t.Fatal(kind)
		}
	}
	if len(client.Actions()) != 0 {
		t.Fatal(client.Actions())
	}
	if _, err := (LoggingExecutor{}).Execute(context.Background(), "dt-ram", model.Action{Type: "SCALE"}); err == nil {
		t.Fatal("logging reported execution")
	}
}
