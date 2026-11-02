#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cluster_name="dt-ram"
cluster_api_host="k3d-${cluster_name}-serverlb"
cluster_config="$repo_root/infrastructure/k3s/k3d.yaml"
dockerfile="$repo_root/Dockerfile.demo"
image="dt-ram/demo:latest"
container_kubeconfig="/tmp/dt-ram-kubeconfig"

fail() {
  printf 'DT-RAM demo launcher: %s\n' "$1" >&2
  exit "${2:-1}"
}

command -v docker >/dev/null 2>&1 || fail 'Docker CLI is required. Install Docker Desktop or Docker Engine and retry.' 127
docker info >/dev/null 2>&1 || fail 'Docker daemon is unavailable. Start Docker Desktop or Docker Engine and retry.'
command -v k3d >/dev/null 2>&1 || fail 'k3d is required to create the local Kubernetes cluster. Install k3d and retry.' 127

[[ -f "$cluster_config" ]] || fail "expected k3d config at $cluster_config"
[[ -f "$dockerfile" ]] || fail "expected demo Dockerfile at $dockerfile"

if k3d cluster get "$cluster_name" >/dev/null 2>&1; then
  printf 'Using existing k3d cluster: %s\n' "$cluster_name"
else
  printf 'Creating k3d cluster: %s\n' "$cluster_name"
  k3d cluster create --config "$cluster_config" || fail "could not create k3d cluster '$cluster_name'"
fi

printf 'Building demo image: %s\n' "$image"
docker build --file "$dockerfile" --tag "$image" "$repo_root" || fail "could not build image '$image'"

tmp_kubeconfig="$(mktemp "${TMPDIR:-/tmp}/dt-ram-kubeconfig.XXXXXX")" || fail 'could not create temporary kubeconfig file'
rewritten_kubeconfig="${tmp_kubeconfig}.rewritten"
trap 'rm -f -- "$tmp_kubeconfig" "$rewritten_kubeconfig"' EXIT
k3d kubeconfig get "$cluster_name" >"$tmp_kubeconfig" || fail "could not read kubeconfig for '$cluster_name'"

# The host-side k3d endpoint is loopback-only. Inside the demo container,
# route that endpoint through Docker's host gateway using the load balancer
# name in the k3d API certificate.
sed -E "s#https://(localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0)(:[0-9]+)?#https://${cluster_api_host}\\2#g" \
  "$tmp_kubeconfig" >"$rewritten_kubeconfig" || fail 'could not prepare a container-reachable kubeconfig'
mv -- "$rewritten_kubeconfig" "$tmp_kubeconfig" || fail 'could not prepare a container-reachable kubeconfig'

printf 'Running shadow-only demo against cluster: %s\n' "$cluster_name"
docker run --rm \
  --add-host="${cluster_api_host}:host-gateway" \
  --volume "$tmp_kubeconfig:$container_kubeconfig:ro" \
  "$image" --kubeconfig "$container_kubeconfig" "$@"
