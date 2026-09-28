#!/usr/bin/env bash
# Local Kubernetes in one command: k3d cluster, images, dev overlay, all healthy.
#
#   scripts/k8s-up.sh          # then open http://civicpulse.localhost:8081
#   k3d cluster delete civicpulse
#
# Needs: docker, k3d (v5), kubectl. Safe to re-run: an existing cluster is
# reused, images are rebuilt and re-imported, and the migrate Job is replaced.
set -euo pipefail

cd "$(dirname "$0")/.."
CLUSTER=civicpulse
NS=civicpulse
TAG=${TAG:-dev}

step() { printf '\n==> %s\n' "$*"; }

step "Cluster"
if k3d cluster list "$CLUSTER" >/dev/null 2>&1; then
  echo "k3d cluster '$CLUSTER' already exists"
else
  k3d cluster create --config k8s/k3d-cluster.yaml
fi
kubectl config use-context "k3d-$CLUSTER" >/dev/null
kubectl apply -f k8s/k3d/traefik-config.yaml
# On a new cluster k3s installs Traefik shortly after start-up: wait for it to exist.
for _ in $(seq 1 90); do
  kubectl -n kube-system get ds/traefik >/dev/null 2>&1 && break
  sleep 2
done
kubectl -n kube-system rollout status ds/traefik --timeout=180s
# VPA recommender (the base manifests include a VerticalPodAutoscaler).
kubectl apply -k k8s/k3d/vpa
kubectl -n kube-system rollout status deploy/vpa-recommender --timeout=180s

step "Images (built here, imported into the cluster; no registry needed)"
docker build -t "ghcr.io/includeduck/scd-civicpulse/backend:$TAG" backend
docker build -t "ghcr.io/includeduck/scd-civicpulse/frontend:$TAG" frontend
k3d image import "ghcr.io/includeduck/scd-civicpulse/backend:$TAG" "ghcr.io/includeduck/scd-civicpulse/frontend:$TAG" -c "$CLUSTER"

step "Deploy (k8s/overlays/dev)"
# A Job's pod template is immutable: replace it so migrations run again.
kubectl -n "$NS" delete job migrate --ignore-not-found
kubectl apply -k k8s/overlays/dev
kubectl -n "$NS" wait --for=condition=complete job/migrate --timeout=300s
kubectl -n "$NS" rollout status deploy/backend --timeout=300s
kubectl -n "$NS" rollout status deploy/frontend --timeout=180s

step "Ready"
kubectl -n "$NS" get pods -o wide
cat <<EOF

  App      http://civicpulse.localhost:8081
  API      http://civicpulse.localhost:8081/api/stats

  If civicpulse.localhost doesn't resolve on your machine:
    curl --resolve civicpulse.localhost:8081:127.0.0.1 http://civicpulse.localhost:8081/api/stats
EOF
