"""TestScribe Flask API — REST endpoints + lightweight dashboard.

Endpoints:
  POST /api/enrich          — enrich a single bug report
  POST /api/enrich/batch    — enrich a list of reports
  GET  /api/reports         — list all enriched reports (in-memory store)
  GET  /api/trends          — pattern and severity distribution stats
  GET  /health              — liveness check
  GET  /                    — HTML dashboard
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, render_template_string, Response

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas import RawReport
from core.orchestrator import Orchestrator

app = Flask(__name__)

# In-memory report store (replaced by persistent DB in production)
_REPORT_STORE: list[dict] = []

_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        force_fallback = not bool(os.environ.get("ANTHROPIC_API_KEY"))
        _orchestrator = Orchestrator(force_fallback=force_fallback)
    return _orchestrator


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.route("/health")
def health() -> Response:
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/api/enrich", methods=["POST"])
def enrich_one() -> Response:
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "JSON body required"}), 400

    try:
        raw = RawReport(**body)
    except Exception as e:
        return jsonify({"error": f"Validation error: {e}"}), 422

    try:
        result = get_orchestrator().enrich(raw)
    except Exception as e:
        return jsonify({"error": f"Enrichment failed: {e}"}), 500

    report_dict = result.model_dump(mode="json")
    _REPORT_STORE.append(report_dict)
    return jsonify(report_dict), 201


@app.route("/api/enrich/batch", methods=["POST"])
def enrich_batch() -> Response:
    body = request.get_json(silent=True)
    if not isinstance(body, list):
        return jsonify({"error": "JSON array of reports required"}), 400

    results = []
    errors = []
    orch = get_orchestrator()

    for i, item in enumerate(body):
        try:
            raw = RawReport(**item)
            report = orch.enrich(raw)
            d = report.model_dump(mode="json")
            _REPORT_STORE.append(d)
            results.append(d)
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    return jsonify({"enriched": len(results), "errors": errors, "reports": results}), 201


@app.route("/api/reports")
def list_reports() -> Response:
    sector = request.args.get("sector")
    pattern = request.args.get("pattern")
    priority = request.args.get("priority")

    filtered = _REPORT_STORE
    if sector:
        filtered = [r for r in filtered if r.get("compliance", {}).get("sector") == sector]
    if pattern:
        filtered = [r for r in filtered if r.get("pattern") == pattern.upper()]
    if priority:
        filtered = [r for r in filtered
                    if r.get("severity", {}).get("priority") == priority.lower()]

    return jsonify({"total": len(filtered), "reports": filtered})


@app.route("/api/trends")
def trends() -> Response:
    from collections import Counter

    patterns: Counter = Counter()
    priorities: Counter = Counter()
    sectors: Counter = Counter()
    by_sectors: Counter = Counter()

    for r in _REPORT_STORE:
        patterns[r.get("pattern", "UNKNOWN")] += 1
        priorities[r.get("severity", {}).get("priority", "unknown")] += 1
        sectors[r.get("compliance", {}).get("sector", "generic")] += 1

    return jsonify({
        "total_reports": len(_REPORT_STORE),
        "patterns": dict(patterns.most_common()),
        "priorities": dict(priorities.most_common()),
        "sectors": dict(sectors.most_common()),
    })


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TestScribe — Bug Report Enricher</title>
<style>
  :root{--bg:#0f1117;--surface:#1a1d2e;--border:#2d3150;--accent:#7c6af7;
    --accent2:#4fc3f7;--text:#e2e8f0;--muted:#94a3b8;--critical:#ef4444;
    --high:#f97316;--medium:#eab308;--low:#22c55e;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}
  header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 24px;
    display:flex;align-items:center;gap:12px}
  header h1{font-size:18px;font-weight:700;color:var(--accent)}
  header span{color:var(--muted);font-size:12px}
  .badge{background:var(--accent);color:#fff;padding:2px 8px;border-radius:12px;font-size:11px}
  main{max-width:1200px;margin:0 auto;padding:24px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px}
  .card h2{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:16px}
  .form-row{display:flex;gap:8px;margin-bottom:16px}
  textarea{width:100%;background:#0f1117;border:1px solid var(--border);color:var(--text);
    border-radius:6px;padding:10px;font-size:13px;resize:vertical;font-family:inherit}
  select,input{background:#0f1117;border:1px solid var(--border);color:var(--text);
    border-radius:6px;padding:8px 10px;font-size:13px;font-family:inherit}
  button{background:var(--accent);color:#fff;border:none;border-radius:6px;
    padding:9px 18px;font-size:13px;cursor:pointer;font-weight:600;transition:.15s}
  button:hover{opacity:.85} button:disabled{opacity:.4;cursor:not-allowed}
  #output{font-family:'Courier New',monospace;font-size:12px;white-space:pre-wrap;
    background:#0a0c14;border:1px solid var(--border);border-radius:6px;
    padding:16px;min-height:120px;max-height:360px;overflow:auto;color:var(--accent2)}
  .stat{display:flex;flex-direction:column;align-items:center;padding:12px;
    background:#0f1117;border-radius:8px}
  .stat-val{font-size:28px;font-weight:700;color:var(--accent)}
  .stat-label{font-size:11px;color:var(--muted);margin-top:4px}
  .stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}
  .bar-item{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:12px}
  .bar-bg{flex:1;background:#0f1117;border-radius:4px;height:8px;overflow:hidden}
  .bar-fill{height:100%;border-radius:4px;background:var(--accent);transition:.3s}
  .priority-critical{color:var(--critical)} .priority-high{color:var(--high)}
  .priority-medium{color:var(--medium)} .priority-low{color:var(--low)}
  #status{font-size:12px;color:var(--muted);margin-top:8px}
  .tag{display:inline-block;padding:2px 7px;border-radius:10px;font-size:11px;
    background:rgba(124,106,247,.15);color:var(--accent);margin-right:4px}
</style>
</head>
<body>
<header>
  <h1>⚡ TestScribe</h1>
  <span>AI-powered Bug Report Enricher</span>
  <span class="badge">v0.2.0</span>
</header>
<main>
  <div class="grid">
    <div class="card" style="grid-column:1/-1">
      <h2>Enrich a Bug Report</h2>
      <div class="form-row">
        <input id="title" placeholder="Title (optional)" style="flex:2">
        <input id="component" placeholder="Component" style="flex:1">
        <select id="sector">
          <option value="generic">Generic</option>
          <option value="fintech">Fintech</option>
          <option value="medtech">Medtech</option>
        </select>
      </div>
      <textarea id="description" rows="4" placeholder="Paste your raw bug report here…"></textarea>
      <div style="display:flex;align-items:center;gap:12px;margin-top:12px">
        <button id="enrichBtn" onclick="enrichReport()">⚡ Enrich Report</button>
        <button onclick="loadTrends()" style="background:var(--surface);border:1px solid var(--border)">
          📊 Refresh Stats
        </button>
        <span id="status"></span>
      </div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>Enriched Output</h2>
      <div id="output">Enriched report will appear here…</div>
    </div>
    <div class="card">
      <h2>Pipeline Stats</h2>
      <div class="stats-row" id="statsRow">
        <div class="stat"><span class="stat-val" id="statTotal">—</span><span class="stat-label">Reports</span></div>
        <div class="stat"><span class="stat-val priority-critical" id="statCritical">—</span><span class="stat-label">Critical</span></div>
        <div class="stat"><span class="stat-val priority-high" id="statHigh">—</span><span class="stat-label">High</span></div>
        <div class="stat"><span class="stat-val priority-medium" id="statMedium">—</span><span class="stat-label">Medium</span></div>
      </div>
      <h2 style="margin-bottom:10px">Top Patterns</h2>
      <div id="patternsChart"></div>
    </div>
  </div>
</main>
<script>
async function enrichReport() {
  const btn = document.getElementById('enrichBtn');
  const status = document.getElementById('status');
  const out = document.getElementById('output');
  const description = document.getElementById('description').value.trim();
  if (!description) { status.textContent = '⚠ Description required'; return; }

  btn.disabled = true; status.textContent = 'Enriching…';
  try {
    const body = {
      description,
      title: document.getElementById('title').value || null,
      component: document.getElementById('component').value || null,
      sector: document.getElementById('sector').value,
    };
    const res = await fetch('/api/enrich', {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) { out.textContent = 'Error: ' + JSON.stringify(data, null, 2); }
    else {
      out.textContent = JSON.stringify(data, null, 2);
      status.textContent = `✅ Enriched as ${data.pattern} · ${data.severity?.priority?.toUpperCase()}`;
      loadTrends();
    }
  } catch(e) { out.textContent = 'Network error: ' + e; }
  finally { btn.disabled = false; }
}

async function loadTrends() {
  try {
    const res = await fetch('/api/trends');
    const data = await res.json();
    document.getElementById('statTotal').textContent = data.total_reports;
    document.getElementById('statCritical').textContent = data.priorities?.critical || 0;
    document.getElementById('statHigh').textContent = data.priorities?.high || 0;
    document.getElementById('statMedium').textContent = data.priorities?.medium || 0;

    const patterns = data.patterns || {};
    const max = Math.max(...Object.values(patterns).map(Number), 1);
    const chart = document.getElementById('patternsChart');
    chart.innerHTML = Object.entries(patterns).slice(0, 6).map(([k, v]) =>
      `<div class="bar-item">
        <span style="width:160px;color:var(--muted)">${k}</span>
        <div class="bar-bg"><div class="bar-fill" style="width:${(Number(v)/max*100).toFixed(0)}%"></div></div>
        <span style="color:var(--accent);width:20px;text-align:right">${v}</span>
      </div>`
    ).join('');
  } catch(e) {}
}

loadTrends();
</script>
</body>
</html>"""


@app.route("/")
def dashboard() -> str:
    return _DASHBOARD_HTML


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(debug=True, port=port)
