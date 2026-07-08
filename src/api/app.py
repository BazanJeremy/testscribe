"""TestScribe Flask API — REST endpoints + dashboard.

Endpoints:
  POST /api/enrich          — enrich a single bug report
  POST /api/enrich/batch    — enrich a list of reports
  GET  /api/reports         — list enriched reports (filterable)
  GET  /api/trends          — pattern/severity/sector stats
  GET  /health              — liveness check
  GET  /                    — HTML dashboard
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, Response

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas import RawReport
from core.orchestrator import Orchestrator

app = Flask(__name__)

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
    results, errors = [], []
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

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TestScribe — Bug Report Enricher</title>
<style>
:root{
  --bg:#0d0f1a;--surface:#141728;--surface2:#1c2035;--border:#252a45;
  --accent:#7c6af7;--accent2:#4fc3f7;--text:#e2e8f0;--muted:#6b7a9e;
  --critical:#ef4444;--high:#f97316;--medium:#eab308;--low:#22c55e;
  --radius:8px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;line-height:1.5}

/* ── Header ── */
header{background:var(--surface);border-bottom:1px solid var(--border);
  padding:12px 24px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:100}
header h1{font-size:16px;font-weight:700;color:var(--accent);letter-spacing:-.01em}
.badge{background:rgba(124,106,247,.18);color:var(--accent);padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600}
.header-right{margin-left:auto;display:flex;align-items:center;gap:10px}
#totalBadge{background:var(--surface2);border:1px solid var(--border);color:var(--muted);
  padding:3px 10px;border-radius:12px;font-size:11px}

/* ── Layout ── */
main{max-width:1280px;margin:0 auto;padding:20px 24px;display:grid;gap:16px}
.top-row{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px}
.mid-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}

/* ── Cards ── */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px}
.card-title{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:14px}

/* ── Stat cards ── */
.stat-card{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px 12px;text-align:center}
.stat-val{font-size:32px;font-weight:800;line-height:1}
.stat-label{font-size:11px;color:var(--muted);margin-top:6px}

/* ── Enrich form ── */
.form-grid{display:grid;grid-template-columns:1fr 1fr auto;gap:8px;margin-bottom:10px}
.form-full{grid-column:1/-1}
input,select,textarea{
  background:var(--bg);border:1px solid var(--border);color:var(--text);
  border-radius:6px;padding:8px 10px;font-size:13px;font-family:inherit;
  transition:border-color .15s;width:100%
}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent)}
textarea{resize:vertical;min-height:72px}
.btn{background:var(--accent);color:#fff;border:none;border-radius:6px;
  padding:9px 16px;font-size:13px;cursor:pointer;font-weight:600;transition:.15s;white-space:nowrap}
.btn:hover{opacity:.85}.btn:disabled{opacity:.35;cursor:not-allowed}
.btn-ghost{background:var(--surface2);border:1px solid var(--border);color:var(--muted)}
.btn-ghost:hover{color:var(--text)}
.actions{display:flex;gap:8px;align-items:center;margin-top:10px}
#statusMsg{font-size:12px;color:var(--muted)}

/* ── Output panel ── */
#output{font-family:'Cascadia Code','Fira Code',monospace;font-size:11.5px;
  white-space:pre-wrap;background:var(--bg);border:1px solid var(--border);
  border-radius:6px;padding:14px;min-height:100px;max-height:320px;
  overflow:auto;color:var(--accent2);line-height:1.6}

/* ── Bar chart ── */
.bar-item{display:flex;align-items:center;gap:8px;margin-bottom:7px;font-size:12px}
.bar-label{color:var(--muted);min-width:190px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{flex:1;background:var(--bg);border-radius:4px;height:6px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;background:var(--accent);transition:width .4s ease}
.bar-count{color:var(--accent);min-width:20px;text-align:right;font-variant-numeric:tabular-nums}

/* ── Priority dots ── */
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;flex-shrink:0}
.dot-critical{background:var(--critical)}.dot-high{background:var(--high)}
.dot-medium{background:var(--medium)}.dot-low{background:var(--low)}
.text-critical{color:var(--critical)}.text-high{color:var(--high)}
.text-medium{color:var(--medium)}.text-low{color:var(--low)}

/* ── Reports table ── */
.table-controls{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center}
.table-controls select,.table-controls input{width:auto;padding:6px 10px;font-size:12px}
.table-wrapper{overflow-x:auto;max-height:440px;overflow-y:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
thead th{background:var(--surface2);position:sticky;top:0;z-index:1;
  padding:8px 10px;text-align:left;color:var(--muted);font-weight:600;
  text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--border);white-space:nowrap}
tbody tr{border-bottom:1px solid var(--border);cursor:pointer;transition:.1s}
tbody tr:hover{background:var(--surface2)}
tbody td{padding:8px 10px;vertical-align:middle}
.td-title{max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.td-pattern{font-family:monospace;color:var(--accent2);font-size:11px}
.td-sector{font-size:11px}
.priority-chip{display:inline-flex;align-items:center;padding:2px 7px;border-radius:10px;font-size:11px;font-weight:600}
.chip-critical{background:rgba(239,68,68,.15);color:var(--critical)}
.chip-high{background:rgba(249,115,22,.15);color:var(--high)}
.chip-medium{background:rgba(234,179,8,.15);color:var(--medium)}
.chip-low{background:rgba(34,197,94,.15);color:var(--low)}
.iec-chip{background:rgba(79,195,247,.1);color:var(--accent2);padding:1px 6px;border-radius:8px;font-size:10px}

/* ── Detail modal ── */
#modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:200;
  align-items:center;justify-content:center;padding:24px}
#modal.open{display:flex}
#modalBox{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  max-width:720px;width:100%;max-height:85vh;overflow:auto;padding:24px}
#modalBox h2{font-size:15px;font-weight:700;margin-bottom:16px;color:var(--accent2)}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.detail-block{background:var(--bg);border-radius:6px;padding:12px}
.detail-block h3{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}
.detail-block p,.detail-block li{font-size:12px;color:var(--text);line-height:1.6}
.detail-block ul{padding-left:16px}
.modal-close{float:right;background:none;border:none;color:var(--muted);cursor:pointer;font-size:18px;line-height:1}
.modal-close:hover{color:var(--text)}
.full-width{grid-column:1/-1}

/* ── Empty state ── */
.empty{text-align:center;padding:40px 20px;color:var(--muted)}
.empty p{margin-top:8px;font-size:12px}
</style>
</head>
<body>

<header>
  <h1>⚡ TestScribe</h1>
  <span class="badge">AI Bug Enricher</span>
  <span style="color:var(--muted);font-size:12px">rule-based fallback active</span>
  <div class="header-right">
    <span id="totalBadge">0 reports</span>
  </div>
</header>

<main>

  <!-- ── Top stats row ── -->
  <div class="top-row">
    <div class="card stat-card">
      <div class="stat-val" id="sCritical" style="color:var(--critical)">0</div>
      <div class="stat-label">Critical</div>
    </div>
    <div class="card stat-card">
      <div class="stat-val" id="sHigh" style="color:var(--high)">0</div>
      <div class="stat-label">High</div>
    </div>
    <div class="card stat-card">
      <div class="stat-val" id="sMedium" style="color:var(--medium)">0</div>
      <div class="stat-label">Medium</div>
    </div>
    <div class="card stat-card">
      <div class="stat-val" id="sLow" style="color:var(--low)">0</div>
      <div class="stat-label">Low</div>
    </div>
  </div>

  <!-- ── Mid row: form + chart ── -->
  <div class="mid-row">

    <div class="card">
      <div class="card-title">Enrich a Bug Report</div>
      <div class="form-grid">
        <input id="fTitle" placeholder="Title (optional)">
        <input id="fComponent" placeholder="Component (optional)">
        <select id="fSector">
          <option value="generic">Generic</option>
          <option value="fintech">Fintech</option>
          <option value="medtech">Medtech</option>
        </select>
        <textarea id="fDesc" class="form-full" placeholder="Paste your raw bug report here — even 'button doesn't work' works…" rows="4"></textarea>
      </div>
      <div class="actions">
        <button class="btn" id="enrichBtn" onclick="enrichReport()">⚡ Enrich</button>
        <button class="btn btn-ghost" onclick="loadSeed()">📂 Load Seed Reports</button>
        <span id="statusMsg"></span>
      </div>
      <div style="margin-top:12px">
        <div class="card-title" style="margin-bottom:8px">Output</div>
        <div id="output">Enriched report will appear here…</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Pattern Distribution</div>
      <div id="patternsChart" style="min-height:120px">
        <div class="empty">⟳ Enrich a report to see pattern trends</div>
      </div>
      <div style="margin-top:20px">
        <div class="card-title" style="margin-bottom:10px">Sectors</div>
        <div id="sectorsChart"></div>
      </div>
    </div>

  </div>

  <!-- ── Reports table ── -->
  <div class="card">
    <div class="card-title">Enriched Reports</div>
    <div class="table-controls">
      <select id="filterSector" onchange="renderTable()">
        <option value="">All sectors</option>
        <option value="medtech">🏥 Medtech</option>
        <option value="fintech">🏦 Fintech</option>
        <option value="generic">🔧 Generic</option>
      </select>
      <select id="filterPriority" onchange="renderTable()">
        <option value="">All priorities</option>
        <option value="critical">Critical</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
      </select>
      <select id="filterPattern" onchange="renderTable()">
        <option value="">All patterns</option>
        <option>AUTH_FLOW</option><option>DATA_VALIDATION</option>
        <option>DATA_INTEGRITY</option><option>PERFORMANCE</option>
        <option>SAFETY_CRITICAL</option><option>SECURITY</option>
        <option>COMPLIANCE_REGULATORY</option><option>INTEGRATION</option>
        <option>UI_REGRESSION</option>
      </select>
      <input id="filterSearch" placeholder="Search title…" oninput="renderTable()" style="min-width:160px">
      <button class="btn btn-ghost" onclick="clearFilters()" style="padding:6px 12px;font-size:12px">✕ Clear</button>
      <span id="tableCount" style="margin-left:auto;color:var(--muted);font-size:12px"></span>
    </div>
    <div class="table-wrapper">
      <table id="reportsTable">
        <thead>
          <tr>
            <th>#</th><th>Title</th><th>Pattern</th><th>Priority</th>
            <th>Score</th><th>Sector</th><th>Compliance</th><th>Conf.</th>
          </tr>
        </thead>
        <tbody id="tableBody">
          <tr><td colspan="8"><div class="empty">⟳ No reports yet — enrich one above or load seed reports</div></td></tr>
        </tbody>
      </table>
    </div>
  </div>

</main>

<!-- ── Detail modal ── -->
<div id="modal" onclick="closeModal(event)">
  <div id="modalBox">
    <button class="modal-close" onclick="closeModalDirect()">✕</button>
    <h2 id="modalTitle">Report Detail</h2>
    <div class="detail-grid" id="modalContent"></div>
  </div>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
let _reports = [];

// ── Enrich ─────────────────────────────────────────────────────────────────
async function enrichReport() {
  const btn = document.getElementById('enrichBtn');
  const status = document.getElementById('statusMsg');
  const out = document.getElementById('output');
  const desc = document.getElementById('fDesc').value.trim();
  if (!desc) { status.textContent = '⚠ Description required'; return; }

  btn.disabled = true;
  status.textContent = 'Enriching…';
  try {
    const body = {
      description: desc,
      title: document.getElementById('fTitle').value || null,
      component: document.getElementById('fComponent').value || null,
      sector: document.getElementById('fSector').value,
    };
    const res = await fetch('/api/enrich', {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) {
      out.textContent = 'Error: ' + (data.error || JSON.stringify(data, null, 2));
      status.textContent = '✗ Error';
    } else {
      out.textContent = JSON.stringify(data, null, 2);
      status.textContent = `✓ ${data.pattern} · ${(data.severity?.priority||'').toUpperCase()}`;
      await refresh();
    }
  } catch(e) { out.textContent = 'Network error: ' + e; status.textContent = '✗'; }
  finally { btn.disabled = false; }
}

// ── Load seed reports ───────────────────────────────────────────────────────
async function loadSeed() {
  const status = document.getElementById('statusMsg');
  status.textContent = 'Loading 30 seed reports…';
  const seedDesc = [
    {description:"The occlusion alarm on the infusion pump display doesn't sound when the IV line is blocked.",title:"Infusion pump alarm doesn't trigger",sector:"medtech"},
    {description:"When entering patient weight as 72.5kg and drug concentration 250mg/500ml, the calculator shows wrong result.",title:"Dosage calculator wrong result",sector:"medtech"},
    {description:"A TOTP code generated 4 minutes ago was still accepted for login.",title:"2FA code accepted after expiry",sector:"fintech"},
    {description:"Entering -500 in the wire transfer amount field processes as a credit to the sender.",title:"Wire transfer allows negative values",sector:"fintech"},
    {description:"The submit button on the checkout page doesn't do anything when clicked.",title:"Button doesn't work",sector:"generic"},
    {description:"The main dashboard crashes immediately upon loading with a JavaScript TypeError.",title:"Dashboard crashes on open",sector:"generic"},
    {description:"Account freeze does not block outgoing API transfers, only UI transfers.",title:"Account freeze bypass via API",sector:"fintech"},
    {description:"Session timeout of 15 minutes not enforced on shared ward workstations.",title:"Session timeout not enforced",sector:"medtech"},
    {description:"Uploading files larger than 50MB fails with no error message.",title:"Large file upload fails silently",sector:"generic"},
    {description:"DICOM images from Siemens scanner display rotated 90 degrees clockwise.",title:"DICOM image wrong orientation",sector:"medtech"},
  ];
  let ok = 0;
  for (const item of seedDesc) {
    try {
      const res = await fetch('/api/enrich', {
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)
      });
      if (res.ok) ok++;
    } catch(e) {}
  }
  status.textContent = `✓ Loaded ${ok} reports`;
  await refresh();
}

// ── Refresh all data ────────────────────────────────────────────────────────
async function refresh() {
  try {
    const [rRes, tRes] = await Promise.all([
      fetch('/api/reports'), fetch('/api/trends')
    ]);
    const rData = await rRes.json();
    const tData = await tRes.json();
    _reports = rData.reports || [];
    updateStats(tData);
    renderCharts(tData);
    renderTable();
    document.getElementById('totalBadge').textContent = `${_reports.length} report${_reports.length!==1?'s':''}`;
  } catch(e) { console.error(e); }
}

// ── Stats ───────────────────────────────────────────────────────────────────
function updateStats(t) {
  const p = t.priorities || {};
  document.getElementById('sCritical').textContent = p.critical || 0;
  document.getElementById('sHigh').textContent     = p.high     || 0;
  document.getElementById('sMedium').textContent   = p.medium   || 0;
  document.getElementById('sLow').textContent      = p.low      || 0;
}

// ── Charts ──────────────────────────────────────────────────────────────────
function renderCharts(t) {
  const patterns = t.patterns || {};
  const sectors  = t.sectors  || {};
  const maxP = Math.max(...Object.values(patterns).map(Number), 1);
  const maxS = Math.max(...Object.values(sectors).map(Number), 1);

  const patEl = document.getElementById('patternsChart');
  const entries = Object.entries(patterns).sort((a,b)=>b[1]-a[1]);
  if (!entries.length) { patEl.innerHTML = '<div class="empty">No data yet</div>'; return; }
  patEl.innerHTML = entries.map(([k,v]) => `
    <div class="bar-item" onclick="filterByPattern('${k}')" style="cursor:pointer" title="Filter by ${k}">
      <span class="bar-label">${k}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(Number(v)/maxP*100).toFixed(0)}%"></div></div>
      <span class="bar-count">${v}</span>
    </div>`).join('');

  const secEl = document.getElementById('sectorsChart');
  const ICONS = {medtech:'🏥',fintech:'🏦',generic:'🔧'};
  secEl.innerHTML = Object.entries(sectors).map(([k,v]) => `
    <div class="bar-item">
      <span class="bar-label">${ICONS[k]||''} ${k}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(Number(v)/maxS*100).toFixed(0)}%;background:var(--accent2)"></div></div>
      <span class="bar-count">${v}</span>
    </div>`).join('');
}

// ── Table ───────────────────────────────────────────────────────────────────
function renderTable() {
  const sector   = document.getElementById('filterSector').value;
  const priority = document.getElementById('filterPriority').value;
  const pattern  = document.getElementById('filterPattern').value;
  const search   = document.getElementById('filterSearch').value.toLowerCase();

  let filtered = _reports.filter(r => {
    if (sector   && r.compliance?.sector !== sector) return false;
    if (priority && r.severity?.priority !== priority) return false;
    if (pattern  && r.pattern !== pattern) return false;
    if (search   && !r.title?.toLowerCase().includes(search)) return false;
    return true;
  });

  document.getElementById('tableCount').textContent =
    filtered.length === _reports.length
      ? `${_reports.length} reports`
      : `${filtered.length} / ${_reports.length} reports`;

  const tbody = document.getElementById('tableBody');
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="8"><div class="empty">No reports match the current filters</div></td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map((r, i) => {
    const p = r.severity?.priority || 'unknown';
    const chipClass = `chip-${p}`;
    const ICONS = {medtech:'🏥',fintech:'🏦',generic:'🔧'};
    const iec = r.compliance?.medtech?.iec_62304_class
      ? `<span class="iec-chip">IEC ${r.compliance.medtech.iec_62304_class}</span>` : '';
    const psd2 = r.compliance?.fintech?.psd2_article
      ? `<span class="iec-chip" title="${r.compliance.fintech.psd2_article}">PSD2</span>` : '';
    const conf = r.confidence_score != null ? `${(r.confidence_score*100).toFixed(0)}%` : '—';
    return `<tr onclick="showDetail(${_reports.indexOf(r)})">
      <td>${i+1}</td>
      <td class="td-title" title="${r.title||''}">${r.title||'—'}</td>
      <td class="td-pattern">${r.pattern||'—'}</td>
      <td><span class="priority-chip ${chipClass}">
        <span class="dot dot-${p}"></span>${p.toUpperCase()}
      </span></td>
      <td>${r.severity?.score ?? '—'}</td>
      <td class="td-sector">${ICONS[r.compliance?.sector]||''} ${r.compliance?.sector||'—'}</td>
      <td>${iec}${psd2}</td>
      <td style="color:var(--muted)">${conf}</td>
    </tr>`;
  }).join('');
}

// ── Detail modal ─────────────────────────────────────────────────────────────
function showDetail(idx) {
  const r = _reports[idx];
  if (!r) return;
  document.getElementById('modalTitle').textContent = r.title || 'Report Detail';
  const sev = r.severity || {};
  const comp = r.compliance || {};
  const steps = (r.reproduction_steps || []).map(s => `<li>${s}</li>`).join('');
  const similar = (r.similar_bugs || []).map(b =>
    `<li>${b.bug_id} — ${b.pattern} (${(b.similarity_score*100).toFixed(0)}% sim)</li>`
  ).join('') || '<li style="color:var(--muted)">None found</li>';

  let compHTML = '';
  if (comp.medtech) {
    const m = comp.medtech;
    compHTML = `<p>IEC 62304 Class: <strong>${m.iec_62304_class}</strong></p>
      <p>SOUP impact: ${m.soup_impact?'Yes':'No'}</p>
      <p>Change control: ${m.change_control_required?'Required':'Not required'}</p>
      <p>Traceability: <code>${m.traceability_tag}</code></p>`;
  } else if (comp.fintech) {
    const f = comp.fintech;
    compHTML = `<p>PSD2: ${f.psd2_article||'N/A'}</p>
      <p>DORA risk: <strong>${f.dora_risk_level}</strong></p>
      <p>AML flag: ${f.aml_flag?'⚠ Yes':'No'}</p>
      <p>Incident reporting: ${f.incident_reporting_required?'Required':'Not required'}</p>`;
  } else {
    compHTML = '<p style="color:var(--muted)">No sector-specific compliance tags</p>';
  }

  document.getElementById('modalContent').innerHTML = `
    <div class="detail-block full-width">
      <h3>Summary</h3><p>${r.summary||r.raw_input||'—'}</p>
    </div>
    <div class="detail-block">
      <h3>Reproduction Steps</h3><ul>${steps||'<li>—</li>'}</ul>
    </div>
    <div class="detail-block">
      <h3>Severity</h3>
      <p>Score: <strong>${sev.score}/10</strong> · ${sev.priority?.toUpperCase()}</p>
      <p>Impact: ${sev.functional_impact} · Repro: ${sev.reproducibility}</p>
      <p>Scope: ${sev.user_scope} · Regression: ${sev.regression_type}</p>
      <p style="color:var(--muted);font-size:11px;margin-top:6px">${sev.rationale||''}</p>
    </div>
    <div class="detail-block">
      <h3>Compliance</h3>${compHTML}
    </div>
    <div class="detail-block">
      <h3>Similar Bugs (RAG)</h3><ul>${similar}</ul>
      <p style="margin-top:6px">Dup. probability: <strong>${((r.duplicate_probability||0)*100).toFixed(0)}%</strong></p>
    </div>
    <div class="detail-block">
      <h3>Environment</h3>
      ${Object.entries(r.environment||{}).map(([k,v])=>`<p>${k}: ${v}</p>`).join('')||'<p style="color:var(--muted)">Unspecified</p>'}
      <p style="margin-top:6px;color:var(--muted);font-size:11px">Enriched by: ${r.enriched_by}</p>
    </div>`;
  document.getElementById('modal').classList.add('open');
}

function closeModal(e) { if (e.target.id === 'modal') closeModalDirect(); }
function closeModalDirect() { document.getElementById('modal').classList.remove('open'); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModalDirect(); });

// ── Filter shortcuts ─────────────────────────────────────────────────────────
function filterByPattern(p) {
  document.getElementById('filterPattern').value = p;
  renderTable();
  document.getElementById('reportsTable').scrollIntoView({behavior:'smooth'});
}
function clearFilters() {
  ['filterSector','filterPriority','filterPattern'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('filterSearch').value = '';
  renderTable();
}

// ── Init ─────────────────────────────────────────────────────────────────────
refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>"""


@app.route("/")
def dashboard() -> str:
    return _DASHBOARD_HTML


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(debug=True, port=port)
