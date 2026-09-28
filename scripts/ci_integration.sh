#!/usr/bin/env bash
# End-to-end check of the Compose stack, as run by CI's `integration` job.
#
# Not "are the containers up" but a real path through every layer: browser ->
# nginx -> FastAPI -> triage -> PostgreSQL, the Redis cache going MISS -> HIT,
# and the network segmentation (frontend has no route to the database).
#
#   bash scripts/ci_integration.sh
#
# Isolated from a developer's own stack: it runs as Compose project
# "civicpulse-ci" (its own containers, network and volumes) with its own env
# file (.env.ci: simulated triage, no Ollama, a random password), and never
# reads or touches .env. It refuses to start while the dev stack's network
# exists, because both use the same host ports and subnet.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=$(command -v python3 || command -v python)
API=http://localhost:8080/api          # through the frontend's nginx, as a browser would
export COMPOSE_PROJECT_NAME=civicpulse-ci
export ENV_FILE=.env.ci                # read by compose.yaml's env_file
COMPOSE="docker compose --env-file .env.ci"

# The dev stack's network uses the same fixed subnet, and exists even when its
# containers are only stopped. `docker compose down` (without -v) removes it
# and keeps the dev stack's data volumes.
if docker network inspect civicpulse_edge >/dev/null 2>&1; then
  echo "The dev stack's network exists (project 'civicpulse'). Run 'docker compose down'" >&2
  echo "first; without -v it keeps your data volumes." >&2
  exit 2
fi

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "::group::docker compose logs (failure)"
    $COMPOSE logs --no-color --tail=200 || true
    echo "::endgroup::"
  fi
  # -v removes only this project's volumes (civicpulse-ci_*), never the dev stack's.
  $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f .env.ci
  exit "$status"
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
json() { "$PY" -c "import json,sys; d=json.load(sys.stdin); print(d$1)"; }

password=$("$PY" -c "import secrets; print(secrets.token_hex(16))")
sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$password/" \
    -e "s/^TRIAGE_PROVIDER=.*/TRIAGE_PROVIDER=simulated/" \
    -e "s/^COMPOSE_PROFILES=.*/COMPOSE_PROFILES=/" \
    .env.example > .env.ci

echo "==> docker compose up (build, then wait for every healthcheck)"
$COMPOSE up -d --build --wait --wait-timeout 300

echo "==> /ready: PostgreSQL and Redis reachable"
for _ in $(seq 1 30); do
  curl -fsS http://localhost:8000/ready >/dev/null && break
  sleep 2
done
curl -fsS http://localhost:8000/ready | grep -q '"ready"' || fail "/ready did not report ready"

echo "==> POST /api/complaints"
created=$(curl -sS -w '\n%{http_code}' -X POST "$API/complaints" -H 'Content-Type: application/json' \
  -d '{"text":"Pipe burst ho gaya hai, paani sarak par beh raha hai","location":"F-8 Markaz, Islamabad"}')
code=$(tail -n1 <<<"$created"); body=$(sed '$d' <<<"$created")
[ "$code" = 201 ] || fail "POST returned $code: $body"
id=$(json "['id']" <<<"$body")
category=$(json "['category']" <<<"$body")
triaged_by=$(json "['triaged_by']" <<<"$body")
echo "    id=$id category=$category triaged_by=$triaged_by"
[ "$category" = water ] || fail "expected category water, got $category"
[ "$triaged_by" = simulated ] || fail "expected triaged_by simulated, got $triaged_by"

echo "==> GET /api/complaints/{id} returns what was stored"
got=$(curl -fsS "$API/complaints/$id")
[ "$(json "['category']" <<<"$got")" = water ] || fail "stored category differs: $got"
[ "$(json "['status']" <<<"$got")" = open ] || fail "new complaint should be open: $got"

echo "==> GET /api/stats: X-Cache MISS, then HIT"
first=$(curl -fsS -D - -o /dev/null "$API/stats" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-cache"{print $2}')
second=$(curl -fsS -D - -o /dev/null "$API/stats" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-cache"{print $2}')
echo "    first=$first second=$second"
[ "$first" = MISS ] || fail "first stats call should be a MISS (the POST invalidates the cache), got '$first'"
[ "$second" = HIT ] || fail "second stats call should be a HIT, got '$second'"

echo "==> Network segmentation: frontend has no route to the database"
if $COMPOSE exec -T frontend nc -z -w 2 database 5432 >/dev/null 2>&1; then
  fail "frontend reached database:5432"
fi
$COMPOSE exec -T backend python -c \
  "import socket; socket.create_connection(('database', 5432), timeout=2)" \
  || fail "positive control: backend could not reach database:5432"

echo "PASS: end-to-end path, cache MISS -> HIT, and network segmentation"
