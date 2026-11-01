package infrastructure

import (
	"gopkg.in/yaml.v3"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestYAMLAndComposeBindSources(t *testing.T) {
	err := filepath.WalkDir(".", func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() || !strings.HasSuffix(path, ".yaml") && !strings.HasSuffix(path, ".yml") {
			return nil
		}
		f, err := os.Open(path)
		if err != nil {
			return err
		}
		defer f.Close()
		decoder := yaml.NewDecoder(f)
		for {
			var doc any
			err = decoder.Decode(&doc)
			if err == io.EOF {
				break
			}
			if err != nil {
				t.Errorf("%s: %v", path, err)
				break
			}
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	var compose struct {
		Services map[string]struct {
			Volumes []string `yaml:"volumes"`
		} `yaml:"services"`
	}
	data, err := os.ReadFile("docker/docker-compose.yml")
	if err != nil {
		t.Fatal(err)
	}
	if err := yaml.Unmarshal(data, &compose); err != nil {
		t.Fatal(err)
	}
	for name, service := range compose.Services {
		for _, volume := range service.Volumes {
			source := strings.Split(volume, ":")[0]
			if strings.HasPrefix(source, ".") {
				if _, err := os.Stat(filepath.Join("docker", source)); err != nil {
					t.Errorf("%s bind source %s: %v", name, source, err)
				}
			}
		}
	}
}

func TestNodeRBACIsReadOnly(t *testing.T) {
	f, err := os.Open("kubernetes/00-namespace-rbac.yaml")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	decoder := yaml.NewDecoder(f)
	found := false
	for {
		var doc struct {
			Kind  string `yaml:"kind"`
			Rules []struct {
				Resources []string `yaml:"resources"`
				Verbs     []string `yaml:"verbs"`
			} `yaml:"rules"`
		}
		err = decoder.Decode(&doc)
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		for _, rule := range doc.Rules {
			for _, resource := range rule.Resources {
				if resource == "nodes" {
					found = true
					if doc.Kind != "ClusterRole" {
						t.Fatal("nodes require a cluster role")
					}
					for _, verb := range rule.Verbs {
						if verb != "get" && verb != "list" {
							t.Fatal("unexpected node privilege", verb)
						}
					}
				}
			}
		}
	}
	if !found {
		t.Fatal("node reader missing")
	}
}

func TestTestbedTelemetryIdentityAndDryRun(t *testing.T) {
	f, err := os.Open("kubernetes/10-go-services.yaml")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	var foundAgent, foundController bool
	decoder := yaml.NewDecoder(f)
	for {
		var doc struct {
			Kind     string `yaml:"kind"`
			Metadata struct {
				Name string `yaml:"name"`
			} `yaml:"metadata"`
			Spec struct {
				Template struct {
					Spec struct {
						HostNetwork                  bool   `yaml:"hostNetwork"`
						ServiceAccountName           string `yaml:"serviceAccountName"`
						AutomountServiceAccountToken *bool  `yaml:"automountServiceAccountToken"`
						Containers                   []struct {
							Env []struct {
								Name      string `yaml:"name"`
								Value     string `yaml:"value"`
								ValueFrom struct {
									FieldRef struct {
										FieldPath string `yaml:"fieldPath"`
									} `yaml:"fieldRef"`
								} `yaml:"valueFrom"`
							} `yaml:"env"`
						} `yaml:"containers"`
					} `yaml:"spec"`
				} `yaml:"template"`
			} `yaml:"spec"`
		}
		if err := decoder.Decode(&doc); err == io.EOF {
			break
		} else if err != nil {
			t.Fatal(err)
		}
		if doc.Kind != "DaemonSet" && doc.Kind != "Deployment" {
			continue
		}
		if doc.Metadata.Name != "telemetry-agent" && doc.Metadata.Name != "infrastructure-controller" {
			continue
		}
		pod := doc.Spec.Template.Spec
		if len(pod.Containers) != 1 {
			t.Fatalf("%s must have one inspected container", doc.Metadata.Name)
		}
		env := map[string]struct{ value, field string }{}
		for _, item := range pod.Containers[0].Env {
			env[item.Name] = struct{ value, field string }{item.Value, item.ValueFrom.FieldRef.FieldPath}
		}
		switch doc.Metadata.Name {
		case "telemetry-agent":
			foundAgent = true
			if doc.Kind != "DaemonSet" || !pod.HostNetwork ||
				pod.AutomountServiceAccountToken == nil || *pod.AutomountServiceAccountToken ||
				env["TELEMETRY_NODE_ID"].field != "spec.nodeName" ||
				env["TELEMETRY_PUBLISH_ENABLED"].value != "true" {
				t.Fatal("telemetry must use the Kubernetes node identity and publish without Kubernetes credentials")
			}
		case "infrastructure-controller":
			foundController = true
			if doc.Kind != "Deployment" || pod.ServiceAccountName != "dt-ram-controller" ||
				env["CONTROLLER_DRY_RUN"].value != "true" {
				t.Fatal("testbed controller must use its restricted account and stay in dry-run mode")
			}
		}
	}
	if !foundAgent || !foundController {
		t.Fatal("testbed telemetry or controller workload is missing")
	}
}
