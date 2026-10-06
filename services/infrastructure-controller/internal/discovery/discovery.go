// Package discovery reads physical inventory without mutating Kubernetes.
package discovery

import (
	"context"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

type Reader interface {
	Nodes(context.Context) (*corev1.NodeList, error)
	Pods(context.Context, string) (*corev1.PodList, error)
}

type Client struct{ Client kubernetes.Interface }

func New(path string) (*Client, error) {
	var cfg *rest.Config
	var err error
	if path == "" {
		cfg, err = rest.InClusterConfig()
	} else {
		cfg, err = clientcmd.BuildConfigFromFlags("", path)
	}
	if err != nil {
		return nil, err
	}
	cfg.Timeout = 10 * 1e9
	client, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		return nil, err
	}
	return &Client{Client: client}, nil
}

func (c *Client) Nodes(ctx context.Context) (*corev1.NodeList, error) {
	return c.Client.CoreV1().Nodes().List(ctx, metav1.ListOptions{})
}

func (c *Client) Pods(ctx context.Context, ns string) (*corev1.PodList, error) {
	return c.Client.CoreV1().Pods(ns).List(ctx, metav1.ListOptions{})
}
