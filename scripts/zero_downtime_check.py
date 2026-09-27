"""Hammer the API while something (a rollout, a pod deletion) happens; count failures.

Standard library only, so it runs anywhere Python does. Every non-2xx response
and every connection error counts as a failure. A zero-downtime rollout must
end with ``failed: 0``.

  python scripts/zero_downtime_check.py --url http://civicpulse.localhost:8081 --seconds 90 &
  kubectl -n civicpulse set image deploy/backend backend=civicpulse/backend:<new-tag> ...

``--resolve-to 127.0.0.1`` connects to that address whatever the URL's host,
for machines where *.localhost doesn't resolve.
"""

from __future__ import annotations

import argparse
import collections
import http.client
import threading
import time
import urllib.parse

PATHS = ("/api/complaints?page_size=5", "/api/stats", "/api/meta/providers")


def worker(url: str, resolve_to: str | None, stop: threading.Event, results: list[tuple[float, str]], lock: threading.Lock) -> None:
    parsed = urllib.parse.urlsplit(url)
    host = resolve_to or parsed.hostname or "localhost"
    port = parsed.port or 80
    i = 0
    while not stop.is_set():
        path = PATHS[i % len(PATHS)]
        i += 1
        started = time.monotonic()
        try:
            conn = http.client.HTTPConnection(host, port, timeout=10)
            conn.request("GET", path, headers={"Host": parsed.netloc})
            status = conn.getresponse().status
            conn.close()
            outcome = str(status)
        except OSError as exc:
            outcome = type(exc).__name__
        with lock:
            results.append((started, outcome))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--resolve-to", default=None)
    args = parser.parse_args()

    stop = threading.Event()
    lock = threading.Lock()
    results: list[tuple[float, str]] = []
    threads = [
        threading.Thread(target=worker, args=(args.url, args.resolve_to, stop, results, lock), daemon=True)
        for _ in range(args.concurrency)
    ]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    try:
        while time.monotonic() - t0 < args.seconds:
            time.sleep(10)
            with lock:
                window = [o for s, o in results if s >= time.monotonic() - 10]
            bad = sum(1 for o in window if not o.startswith("2"))
            print(f"t={time.monotonic() - t0:5.0f}s  last 10 s: {len(window):5d} requests, {bad} failed", flush=True)
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=15)

    counts = collections.Counter(o for _, o in results)
    failed = sum(n for o, n in counts.items() if not o.startswith("2"))
    print(f"total: {len(results)} requests in {time.monotonic() - t0:.0f} s; outcomes: {dict(counts)}; failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
