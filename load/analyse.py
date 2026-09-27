"""Turn one load-test run into lag numbers and a replicas-vs-load chart.

  python load/analyse.py docs/evidence/load/<run>

Reads samples.csv (hpa_sampler.py), k6-start-epoch and k6-summary.json from
the run directory, and the offered-load schedule from load/k6-script.js (so
the chart plots exactly what k6 was told to offer). Writes summary.md and
chart.svg next to them. Standard library only.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("k6-script.js")


def schedule() -> list[tuple[float, float]]:
    """(duration_s, target_rps) stages from the SCHEDULE constant in k6-script.js."""
    body = SCRIPT.read_text(encoding="utf-8").split("export const SCHEDULE", 1)[1].split("];", 1)[0]
    stages = re.findall(r'target:\s*(\d+),\s*duration:\s*"(\d+)s"', body)
    return [(float(d), float(t)) for t, d in stages]


def offered_at(t: float, stages: list[tuple[float, float]], start_rate: float) -> float:
    """Offered requests/s at t seconds after k6 started (linear ramps between stage targets)."""
    elapsed, previous = 0.0, start_rate
    for duration, target in stages:
        if t <= elapsed + duration:
            return previous + (target - previous) * ((t - elapsed) / duration)
        elapsed, previous = elapsed + duration, target
    return 0.0


def load(run: Path) -> tuple[list[dict[str, float | None]], float]:
    k6_start = float((run / "k6-start-epoch").read_text().strip())
    rows = []
    with open(run / "samples.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            def num(key: str) -> float | None:
                return float(r[key]) if r.get(key) not in (None, "") else None

            rows.append(
                {
                    "t": float(r["epoch"]) - k6_start,
                    "cpu": num("cpu_utilisation_pct"),
                    "desired": num("desired_replicas"),
                    "ready": num("ready_replicas"),
                    "request": r.get("cpu_request") or "",
                }
            )
    return rows, k6_start


def first(rows: list[dict], after: float, pred) -> float | None:
    return next((r["t"] for r in rows if r["t"] >= after and pred(r)), None)


def svg_chart(rows: list[dict], stages: list[tuple[float, float]], marks: dict[str, float | None], title: str) -> str:
    width, height = 900, 520
    left, right, top = 60, 60, 40
    panel_h, gap = 190, 50
    t_min, t_max = min(r["t"] for r in rows), max(r["t"] for r in rows)
    peak_rps = max(t for _, t in stages) * 1.15
    max_cpu = max([r["cpu"] or 0 for r in rows] + [100]) * 1.1
    max_rep = 11

    def x(t: float) -> float:
        return left + (t - t_min) / (t_max - t_min) * (width - left - right)

    def y(v: float, vmax: float, panel: int) -> float:
        base = top + panel * (panel_h + gap) + panel_h
        return base - v / vmax * panel_h

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="system-ui, sans-serif" font-size="12">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="22" font-size="15" font-weight="600">{title}</text>',
    ]
    for panel, (label_l, label_r) in enumerate([("offered load (req/s)", "CPU / request (%)"), ("replicas", "")]):
        py0, py1 = top + panel * (panel_h + gap), top + panel * (panel_h + gap) + panel_h
        out.append(f'<rect x="{left}" y="{py0}" width="{width - left - right}" height="{panel_h}" fill="none" stroke="#ccc"/>')
        out.append(f'<text x="{left - 8}" y="{py0 - 6}" fill="#1f6fb2">{label_l}</text>')
        if label_r:
            out.append(f'<text x="{width - right}" y="{py0 - 6}" text-anchor="end" fill="#b7791f">{label_r}</text>')
    # axes ticks
    for v in range(0, int(peak_rps) + 1, 25):
        yy = y(v, peak_rps, 0)
        out.append(f'<text x="{left - 6}" y="{yy + 4}" text-anchor="end" fill="#555">{v}</text>')
    for v in range(0, int(max_cpu) + 1, 50):
        yy = y(v, max_cpu, 0)
        out.append(f'<text x="{width - right + 6}" y="{yy + 4}" fill="#555">{v}</text>')
    out.append(f'<line x1="{left}" x2="{width - right}" y1="{y(60, max_cpu, 0)}" y2="{y(60, max_cpu, 0)}" stroke="#b7791f" stroke-dasharray="2 3"/>')
    out.append(f'<text x="{width - right - 4}" y="{y(60, max_cpu, 0) - 4}" text-anchor="end" fill="#b7791f">HPA target 60 %</text>')
    for v in range(0, max_rep, 2):
        yy = y(v, max_rep, 1)
        out.append(f'<text x="{left - 6}" y="{yy + 4}" text-anchor="end" fill="#555">{v}</text>')
    for t in range(0, int(t_max) + 1, 60):
        if t >= t_min:
            out.append(f'<text x="{x(t)}" y="{top + 2 * panel_h + gap + 18}" text-anchor="middle" fill="#555">{t}s</text>')
            out.append(f'<line x1="{x(t)}" x2="{x(t)}" y1="{top}" y2="{top + 2 * panel_h + gap}" stroke="#eee"/>')
    # offered load (area), from the schedule
    ts = [t_min + i * (t_max - t_min) / 400 for i in range(401)]
    pts = " ".join(f"{x(t):.1f},{y(offered_at(t, stages, 5) if t >= 0 else 0, peak_rps, 0):.1f}" for t in ts)
    out.append(f'<polyline points="{pts}" fill="none" stroke="#1f6fb2" stroke-width="2"/>')
    # CPU utilisation
    cpu = " ".join(f"{x(r['t']):.1f},{y(r['cpu'], max_cpu, 0):.1f}" for r in rows if r["cpu"] is not None)
    out.append(f'<polyline points="{cpu}" fill="none" stroke="#b7791f" stroke-width="1.5"/>')

    def step(key: str, color: str, dash: str = "") -> None:
        pts, prev = [], None
        for r in rows:
            if r[key] is None:
                continue
            if prev is not None:
                pts.append(f"{x(r['t']):.1f},{y(prev, max_rep, 1):.1f}")
            pts.append(f"{x(r['t']):.1f},{y(r[key], max_rep, 1):.1f}")
            prev = r[key]
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2" {dash}/>')

    step("desired", "#a4262c", 'stroke-dasharray="6 3"')
    step("ready", "#0b6b5d")
    out.append(f'<text x="{left + 8}" y="{top + panel_h + gap + 16}" fill="#a4262c">desired (HPA)</text>')
    out.append(f'<text x="{left + 110}" y="{top + panel_h + gap + 16}" fill="#0b6b5d">ready pods</text>')
    for label, t in marks.items():
        if t is not None:
            out.append(f'<line x1="{x(t)}" x2="{x(t)}" y1="{top}" y2="{top + 2 * panel_h + gap}" stroke="#888" stroke-dasharray="3 3"/>')
            out.append(f'<text x="{x(t) + 3}" y="{top + 2 * panel_h + gap - 6}" fill="#444" transform="rotate(-90 {x(t) + 3},{top + 2 * panel_h + gap - 6})">{label}</text>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    run = Path(sys.argv[1])
    stages = schedule()
    rows, _ = load(run)
    load_arrives = stages[0][0]  # the ramp starts after the baseline stage
    initial_ready = next((r["ready"] for r in rows if r["t"] <= load_arrives and r["ready"]), 2)
    initial_desired = next((r["desired"] for r in rows if r["t"] <= load_arrives and r["desired"]), 2)
    t_cpu = first(rows, load_arrives, lambda r: (r["cpu"] or 0) > 60)
    t_desired = first(rows, load_arrives, lambda r: (r["desired"] or 0) > initial_desired)
    t_ready = first(rows, load_arrives, lambda r: (r["ready"] or 0) > initial_ready)
    peak_ready = max((r["ready"] or 0) for r in rows if r["t"] >= load_arrives)
    t_peak = first(rows, load_arrives, lambda r: (r["ready"] or 0) >= peak_ready)
    load_leaves = sum(d for d, _ in stages[:3])
    t_scale_in = first(rows, load_leaves, lambda r: (r["desired"] or 99) < peak_ready)
    peak_cpu = max((r["cpu"] or 0) for r in rows)
    request = next((r["request"] for r in rows if r["request"]), "?")

    summary = {}
    try:
        k6 = json.loads((run / "k6-summary.json").read_text(encoding="utf-8"))
        m = k6["metrics"]
        summary = {
            "requests": int(m["http_reqs"]["count"]),
            "failed_rate": m["http_req_failed"].get("value", m["http_req_failed"].get("rate", 0)),
            "p95_ms": round(m["http_req_duration"]["p(95)"]),
            "p99_ms": round(m["http_req_duration"]["p(99)"]),
            "max_ms": round(m["http_req_duration"]["max"]),
        }
    except (OSError, KeyError, ValueError):
        pass

    def fmt(t: float | None) -> str:
        return "n/a" if t is None else f"{t:.0f} s"

    def lag(t: float | None) -> str:
        return "n/a" if t is None else f"**{t - load_arrives:.0f} s**"

    lines = [
        f"# Load test `{run.name}`",
        "",
        f"CPU request per backend pod: `{request}`. Offered load: {stages[0][1]:.0f} req/s, then "
        f"{max(t for _, t in stages):.0f} req/s from t = {load_arrives:.0f} s to t = {load_leaves:.0f} s "
        "(`load/k6-script.js`, arrival-rate executor). t = 0 is when k6 started.",
        "",
        "| Event | t | Lag after the load arrived |",
        "|---|---|---|",
        f"| Load starts rising | {fmt(load_arrives)} | |",
        f"| HPA first sees CPU above 60 % | {fmt(t_cpu)} | {lag(t_cpu)} |",
        f"| HPA raises desired replicas | {fmt(t_desired)} | {lag(t_desired)} |",
        f"| First extra pod Ready (capacity arrives) | {fmt(t_ready)} | {lag(t_ready)} |",
        f"| Peak of {peak_ready:.0f} ready pods | {fmt(t_peak)} | {lag(t_peak)} |",
        f"| Load leaves | {fmt(load_leaves)} | |",
        f"| HPA starts scaling in | {fmt(t_scale_in)} | {'n/a' if t_scale_in is None else f'{t_scale_in - load_leaves:.0f} s after the load left'} |",
        "",
        f"Peak CPU utilisation reported by the HPA: {peak_cpu:.0f} % of request.",
        "",
    ]
    if summary:
        lines += [
            "| k6 | |",
            "|---|---|",
            f"| Requests | {summary['requests']:,} |",
            f"| Failed | {summary['failed_rate'] * 100:.2f} % |",
            f"| p95 / p99 / max latency | {summary['p95_ms']} / {summary['p99_ms']} / {summary['max_ms']} ms |",
            "",
        ]
    lines.append("![replicas vs offered load](chart.svg)")
    (run / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    marks = {"load arrives": load_arrives, "desired up": t_desired, "capacity arrives": t_ready, "load leaves": load_leaves}
    title = f"Backend replicas vs offered load — {run.name} (CPU request {request})"
    (run / "chart.svg").write_text(svg_chart(rows, stages, marks, title), encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
