# Load tests: HPA lag, and the VPA loop

Two runs of the same test on 2026-09-27: the local k3d cluster (3 nodes, 12 CPUs shared with Docker Desktop), the dev overlay, simulated triage.

**Load** (`load/k6-script.js`): k6's arrival-rate executor offers **5 req/s for 60 s, ramps to 120 req/s over 20 s, holds 240 s**, then drops back. It's a fixed *offered* load: requests start on schedule however slowly earlier ones finish. The mix is 70 % filtered complaint lists (a database query each), 20 % `/api/stats` and 10 % `/api/meta/providers`, through the Ingress.

**Captured per run** (`load/run-load-test.sh <name>`):

- `hpa-watch.txt`: `kubectl get hpa -w`, timestamped
- `samples.csv`: HPA and Deployment every 5 s
- `k6.txt` and `k6-summary.json`
- `hpa-describe.txt`, `vpa-describe.txt`
- `summary.md` (lag table) and `chart.svg` (replicas vs offered load)

## The VPA loop (brief §3.3, steps 1–5)

1. **The requests we guessed** when writing `k8s/base/backend.yaml`: `cpu: 100m`, `memory: 128Mi`.
2. **Load test** → [`before-vpa/`](before-vpa/summary.md).
3. **`kubectl describe vpa backend-vpa`** after that run ([`before-vpa/vpa-describe.txt`](before-vpa/vpa-describe.txt)):

   | | CPU | Memory |
   |---|---|---|
   | Lower bound | 25m | 250Mi |
   | **Target** | **182m** | **250Mi** |
   | Upper bound | 28523m | ~10 GB |

   The upper bound is huge because the recommender had only minutes of history. It narrows as history accumulates, so we act on the target and ignore the bound.
4. **Requests updated** to the target: `cpu: 182m`, `memory: 250Mi` (limits unchanged, 500m / 384Mi).
5. **Same test again** → [`after-vpa/`](after-vpa/summary.md).

## What changed in the HPA's behaviour

| | Before (request 100m) | After (request 182m) |
|---|---|---|
| Load arrives → HPA raises desired replicas | 40 s | 36 s |
| Load arrives → first extra pod Ready | 55 s | 51 s |
| Load arrives → 10 pods Ready | 70 s | 96 s |
| Scale-up steps | 2 → 6 → 10 | 2 → 4 → 7 → 10 |
| Peak CPU utilisation (usage ÷ request) | 500 % | 227 % |
| Utilisation at 10 pods under full load | 62–68 % (above target, at `maxReplicas`) | 36–40 % (below target) |
| Replicas the HPA actually needed at full load | more than 10: capped | about 7 |
| Scale-in began (t) | 645 s: 10 → 8 → 2 | 485 s: 10 → 7, later → 6 → 2 |
| Requests / failed | 31,652 / 0 | 31,887 / 0 |
| p95 / p99 / max latency | 1,148 / 3,213 / 5,840 ms | 21 / 251 / 1,753 ms |

**Reading it:**

- **The request is the HPA's denominator.** The same traffic produced the same CPU *usage* in both runs, but 182m instead of 100m shrank the utilisation the HPA saw by about 45 %.
- **Before**, the guessed request made each pod look overloaded: 10 pods (the maximum) still read above 60 %, so the HPA was pinned at its ceiling and wanted more.
- **After**, the same 10 pods read ~38 %, so the HPA's own maths says 7 are enough. That's why, once the 300 s scale-down window allowed it, it went 10 → 7 rather than holding 10 until the load was long gone.
- **Steps are smaller** because a lower utilisation reading gives a smaller desired count per sync.
- **Why "500 %" before:** it equals limit ÷ request (500m ÷ 100m). Until help arrived, the first two pods were throttled at their CPU limit, which is where the multi-second tail latency came from.
- **Caveat on latency:** we ran each configuration once. The latency difference is larger than the capacity difference explains, so part of it may be run-to-run variance (a warmer database cache for the second run, for example). The HPA numbers come from the controller's own status and are what we rely on.

![before](before-vpa/chart.svg)

![after](after-vpa/chart.svg)
