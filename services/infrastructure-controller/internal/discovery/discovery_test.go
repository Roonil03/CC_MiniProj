package discovery

import (
	"context"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
	"testing"
)

func TestInventoryScope(t *testing.T) {
	client := fake.NewSimpleClientset(
		&corev1.Node{ObjectMeta: metav1.ObjectMeta{Name: "edge-a"}},
		&corev1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "ours", Namespace: "dt-ram"}},
		&corev1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "other", Namespace: "other"}},
	)
	reader := &Client{Client: client}
	nodes, err := reader.Nodes(context.Background())
	if err != nil || len(nodes.Items) != 1 {
		t.Fatal(nodes, err)
	}
	pods, err := reader.Pods(context.Background(), "dt-ram")
	if err != nil || len(pods.Items) != 1 || pods.Items[0].Name != "ours" {
		t.Fatal(pods, err)
	}
	for _, action := range client.Actions() {
		if action.GetVerb() != "list" {
			t.Fatal("unexpected mutation", action)
		}
	}
}
