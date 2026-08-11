#!/usr/bin/env python3
"""Render a 6-panel observability dashboard HTML from data/logs.jsonl + optional /metrics."""

from __future__ import annotations

import json
import math
import statistics
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
OUT_PATH = REPO_ROOT / "submission" / "evidence" / "dashboard.html"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    idx = max(0, min(len(items) - 1, round((p / 100) * len(items) + 0.5) - 1))
    return float(items[idx])


def load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def fetch_metrics(url: str = "http://127.0.0.1:8000/metrics") -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def summarize(events: list[dict]) -> dict:
    received = [e for e in events if e.get("event") == "request_received"]
    failed = [e for e in events if e.get("event") == "request_failed"]
    sent = [e for e in events if e.get("event") == "response_sent"]

    latencies = [float(e["latency_ms"]) for e in sent if e.get("latency_ms") is not None]
    costs = [float(e["cost_usd"]) for e in sent if e.get("cost_usd") is not None]
    tokens_in = [int(e["tokens_in"]) for e in sent if e.get("tokens_in") is not None]
    tokens_out = [int(e["tokens_out"]) for e in sent if e.get("tokens_out") is not None]
    qualities = [float(e["quality_score"]) for e in sent if e.get("quality_score") is not None]
    breakdown = Counter(e.get("error_type") or "Unknown" for e in failed)

    n_recv = len(received) or len(sent)
    n_fail = len(failed)
    error_rate = round(n_fail / n_recv * 100, 2) if n_recv else 0.0

    return {
        "traffic": n_recv,
        "latency_p50": percentile(latencies, 50),
        "latency_p95": percentile(latencies, 95),
        "latency_p99": percentile(latencies, 99),
        "error_rate_pct": error_rate,
        "error_breakdown": dict(breakdown),
        "total_cost_usd": round(sum(costs), 4),
        "avg_cost_usd": round(statistics.mean(costs), 4) if costs else 0.0,
        "tokens_in_total": sum(tokens_in),
        "tokens_out_total": sum(tokens_out),
        "quality_avg": round(statistics.mean(qualities), 4) if qualities else 0.0,
        "responses": len(sent),
    }


def status(ok: bool) -> str:
    return "ok" if ok else "breach"


def render(html_path: Path, log_stats: dict, live: dict | None) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    s = log_stats
    bre_lat = s["latency_p95"] <= 3000
    bre_err = s["error_rate_pct"] <= 2
    bre_cost = s["total_cost_usd"] <= 2.5
    bre_tok = (s["tokens_in_total"] + s["tokens_out_total"]) <= 50000
    bre_q = s["quality_avg"] >= 0.75

    live_block = ""
    if live:
        live_block = f"""
        <div class="live">
          <strong>Live GET /metrics</strong>
          traffic={live.get('traffic')} ·
          p95={live.get('latency_p95')} ms ·
          error={live.get('error_rate_pct')}% ·
          cost=${live.get('total_cost_usd')} ·
          quality={live.get('quality_avg')}
        </div>
        """

    rows_err = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in (s["error_breakdown"] or {"—": 0}).items()
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Day 13 AI Observability Dashboard</title>
  <style>
    :root {{
      --bg: #0f1419;
      --card: #1a2332;
      --text: #e7eef7;
      --muted: #8da2b8;
      --ok: #3dbe8c;
      --bad: #e36a6a;
      --line: #2b3b51;
      --accent: #5b9fd4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background: radial-gradient(circle at top left, #1b2a3d, var(--bg));
      color: var(--text); min-height: 100vh; padding: 24px;
    }}
    header {{
      display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px;
      margin-bottom: 18px; border-bottom: 1px solid var(--line); padding-bottom: 14px;
    }}
    h1 {{ margin: 0; font-size: 1.35rem; letter-spacing: 0.02em; }}
    .meta {{ color: var(--muted); font-size: 0.9rem; line-height: 1.5; }}
    .grid {{
      display: grid; grid-template-columns: repeat(2, minmax(280px, 1fr)); gap: 14px;
    }}
    .panel {{
      background: var(--card); border: 1px solid var(--line); border-radius: 10px;
      padding: 16px 18px; min-height: 160px;
    }}
    .panel h2 {{
      margin: 0 0 6px; font-size: 0.95rem; font-weight: 600; color: var(--accent);
      text-transform: none;
    }}
    .unit {{ color: var(--muted); font-size: 0.78rem; margin-bottom: 10px; }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 14px; margin: 8px 0 12px; }}
    .metric strong {{ display: block; font-size: 1.4rem; }}
    .metric span {{ color: var(--muted); font-size: 0.75rem; }}
    .threshold {{
      font-size: 0.82rem; padding: 6px 8px; border-radius: 6px;
      background: #121a24; border: 1px dashed var(--line);
    }}
    .threshold.ok {{ border-color: var(--ok); color: var(--ok); }}
    .threshold.breach {{ border-color: var(--bad); color: var(--bad); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    td, th {{ padding: 4px 6px; border-bottom: 1px solid var(--line); text-align: left; }}
    .live {{
      margin-top: 14px; padding: 10px 12px; background: #121a24; border-radius: 8px;
      font-size: 0.85rem; color: var(--muted);
    }}
    footer {{ margin-top: 16px; color: var(--muted); font-size: 0.8rem; }}
    @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Day 13 AI Observability</h1>
      <div class="meta">
        Source: <code>data/logs.jsonl</code> · Contract: <code>config/dashboard.yaml</code><br/>
        Time range default: <strong>Last 60 minutes</strong> · Refresh: <strong>30s</strong> (manual reload for this HTML)
      </div>
    </div>
    <div class="meta">Generated: {now}<br/>Tool: Spec HTML renderer (local)</div>
  </header>

  <div class="grid">
    <section class="panel">
      <h2>1. Latency percentiles</h2>
      <div class="unit">Unit: ms · Fields: latency_ms on response_sent</div>
      <div class="metrics">
        <div class="metric"><strong>{s['latency_p50']:.0f}</strong><span>P50</span></div>
        <div class="metric"><strong>{s['latency_p95']:.0f}</strong><span>P95</span></div>
        <div class="metric"><strong>{s['latency_p99']:.0f}</strong><span>P99</span></div>
      </div>
      <div class="threshold {status(bre_lat)}">SLO line: P95 ≤ 3000 ms · current P95 = {s['latency_p95']:.0f} ms</div>
    </section>

    <section class="panel">
      <h2>2. Request traffic</h2>
      <div class="unit">Unit: requests · Events: request_received</div>
      <div class="metrics">
        <div class="metric"><strong>{s['traffic']}</strong><span>total requests (window logs)</span></div>
        <div class="metric"><strong>{s['responses']}</strong><span>responses sent</span></div>
      </div>
      <div class="threshold ok">Threshold: rate ≥ 1 req/min when lab is active</div>
    </section>

    <section class="panel">
      <h2>3. Error rate and breakdown</h2>
      <div class="unit">Unit: percent · Events: request_received / request_failed</div>
      <div class="metrics">
        <div class="metric"><strong>{s['error_rate_pct']:.2f}%</strong><span>error_rate_pct</span></div>
      </div>
      <table><thead><tr><th>error_type</th><th>count</th></tr></thead><tbody>{rows_err}</tbody></table>
      <div class="threshold {status(bre_err)}" style="margin-top:10px">SLO line: error_rate ≤ 2% · current = {s['error_rate_pct']:.2f}%</div>
    </section>

    <section class="panel">
      <h2>4. Cost over time</h2>
      <div class="unit">Unit: usd · Field: cost_usd</div>
      <div class="metrics">
        <div class="metric"><strong>${s['total_cost_usd']:.4f}</strong><span>total_cost_usd</span></div>
        <div class="metric"><strong>${s['avg_cost_usd']:.4f}</strong><span>avg_cost_usd</span></div>
      </div>
      <div class="threshold {status(bre_cost)}">Budget line: total ≤ $2.50 / day · current window total = ${s['total_cost_usd']:.4f}</div>
    </section>

    <section class="panel">
      <h2>5. Input and output tokens</h2>
      <div class="unit">Unit: tokens · Fields: tokens_in, tokens_out</div>
      <div class="metrics">
        <div class="metric"><strong>{s['tokens_in_total']}</strong><span>tokens_in_total</span></div>
        <div class="metric"><strong>{s['tokens_out_total']}</strong><span>tokens_out_total</span></div>
      </div>
      <div class="threshold {status(bre_tok)}">Threshold: sum ≤ 50_000 · current = {s['tokens_in_total'] + s['tokens_out_total']}</div>
    </section>

    <section class="panel">
      <h2>6. Quality proxy</h2>
      <div class="unit">Unit: score 0–1 · Field: quality_score</div>
      <div class="metrics">
        <div class="metric"><strong>{s['quality_avg']:.3f}</strong><span>quality_avg (mean)</span></div>
      </div>
      <div class="threshold {status(bre_q)}">SLO line: mean ≥ 0.75 · current = {s['quality_avg']:.3f}</div>
    </section>
  </div>

  {live_block}

  <footer>
    Spec: docs/dashboard-spec.md · SLO: config/slo.yaml · Alerts: config/alert_rules.yaml + docs/alerts.md<br/>
    Validator: <code>python scripts/validate_dashboard.py</code> → must report 6/6 panel.
  </footer>
</body>
</html>
"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    print(f"Wrote {html_path}")


def main() -> int:
    events = load_events(LOG_PATH)
    stats = summarize(events)
    live = fetch_metrics()
    render(OUT_PATH, stats, live)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
