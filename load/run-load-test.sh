#!/usr/bin/env bash
# One load test against the local k3d cluster, with everything the brief asks
# to capture: `kubectl get hpa -w`, HPA/replica samples, the k6 summary, the
# VPA recommendation, the lag numbers and the replicas-vs-load chart.
#
#   bash load/run-load-test.sh <run-name>     # e.g. before-vpa, after-vpa
#
# Output: docs/evidence/load/<run-name>/. Needs docker, kubectl and python.
set -euo pipefail
cd "$(dirname "$0")/.."

RUN=${1:?usage: load/run-load-test.sh <run-name>}
OUT=docs/evidence/load/$RUN
K6_IMAGE=grafana/k6:2.3.0@sha256:9c2dee7f8ed74d317e4027c06a10f169b625638189de8d4555d0b3486a5aeb34
LOAD_SECONDS=400      # the schedule in load/k6-script.js
OBSERVE=${OBSERVE:-420}  # keep sampling after k6 stops: scale-in waits out a 300 s window
PY=${PYTHON:-python}
HOSTPWD=$(pwd -W 2>/dev/null || pwd)   # Windows path under Git Bash, POSIX path elsewhere
mkdir -p "$OUT"

echo "baseline: $(kubectl -n civicpulse get hpa backend --no-headers)"
( kubectl -n civicpulse get hpa backend -w | while IFS= read -r line; do
    printf '%s  %s\n' "$(date -u +%H:%M:%S)" "$line"; done ) > "$OUT/hpa-watch.txt" 2>&1 &
WATCH=$!
"$PY" load/hpa_sampler.py --out "$OUT/samples.csv" --seconds $((LOAD_SECONDS + OBSERVE + 10)) &
SAMPLER=$!
trap 'kill $WATCH $SAMPLER 2>/dev/null || true' EXIT
sleep 5

date +%s > "$OUT/k6-start-epoch"
echo "k6 running for ${LOAD_SECONDS}s, then observing scale-in for ${OBSERVE}s..."
MSYS_NO_PATHCONV=1 docker run --rm --network k3d-civicpulse \
  -v "$HOSTPWD/load:/load:ro" -v "$HOSTPWD/$OUT:/out" "$K6_IMAGE" \
  run --quiet -e BASE_URL=http://k3d-civicpulse-serverlb --summary-export=/out/k6-summary.json \
  /load/k6-script.js > "$OUT/k6.txt" 2>&1 || echo "k6 reported failed thresholds: see $OUT/k6.txt"

wait "$SAMPLER" || true
kubectl -n civicpulse describe hpa backend > "$OUT/hpa-describe.txt"
kubectl -n civicpulse describe vpa backend-vpa > "$OUT/vpa-describe.txt" 2>&1 || true
"$PY" load/analyse.py "$OUT"
