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
