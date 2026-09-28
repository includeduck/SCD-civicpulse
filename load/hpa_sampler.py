"""Record the HPA and the backend Deployment every few seconds, as CSV.

  python load/hpa_sampler.py --out run/samples.csv --seconds 900

Columns: elapsed_s, epoch, utc, cpu_utilisation_pct (the HPA's own number: usage /
request, averaged over pods), desired_replicas, current_replicas,
ready_replicas, cpu_request (per container, from the Deployment).
Standard library only; shells out to kubectl.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from datetime import UTC, datetime


def kubectl_json(*args: str) -> dict:
    out = subprocess.run(["kubectl", "-n", "civicpulse", *args, "-o", "json"], capture_output=True, text=True, timeout=20)
    return json.loads(out.stdout) if out.returncode == 0 else {}


def sample() -> dict[str, object]:
    hpa = kubectl_json("get", "hpa", "backend")
    deploy = kubectl_json("get", "deployment", "backend")
    status = hpa.get("status", {})
    utilisation = None
    for metric in status.get("currentMetrics") or []:
        resource = metric.get("resource") or {}
        if resource.get("name") == "cpu":
            utilisation = resource.get("current", {}).get("averageUtilization")
    containers = deploy.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    request = next((c.get("resources", {}).get("requests", {}).get("cpu") for c in containers if c.get("name") == "backend"), None)
    return {
        "cpu_utilisation_pct": utilisation,
        "desired_replicas": status.get("desiredReplicas"),
        "current_replicas": status.get("currentReplicas"),
        "ready_replicas": deploy.get("status", {}).get("readyReplicas", 0),
        "cpu_request": request,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--seconds", type=float, default=900)
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args()

    fields = ["elapsed_s", "epoch", "utc", "cpu_utilisation_pct", "desired_replicas", "current_replicas", "ready_replicas", "cpu_request"]
    t0 = time.monotonic()
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        while (elapsed := time.monotonic() - t0) < args.seconds:
            row = {"elapsed_s": round(elapsed, 1), "epoch": round(time.time(), 1), "utc": datetime.now(UTC).strftime("%H:%M:%S"), **sample()}
            writer.writerow(row)
            fh.flush()
            time.sleep(max(0.0, args.interval - (time.monotonic() - t0 - elapsed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
