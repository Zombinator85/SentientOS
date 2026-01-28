"""Read-only FastAPI dashboard exposing SentientOS operator telemetry."""

from __future__ import annotations

import difflib
import json
import os
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from sentientos.admin_server import admin_metrics, admin_status
from sentientos.storage import get_data_root
from embodiment.silhouette_store import load_recent_silhouettes, load_silhouette

app = FastAPI(title="SentientOS Operator Dashboard", docs_url=None, redoc_url=None)


def require_token(request: Request) -> None:
    """Enforce bearer token authentication when configured."""

    expected = os.environ.get("SENTIENTOS_DASHBOARD_TOKEN")
    if not expected:
        return
    provided = request.headers.get("Authorization", "")
    if not provided.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = provided.split(" ", 1)[1]
    if token != expected:
        raise HTTPException(status_code=403, detail="invalid dashboard token")


def _fetch_status() -> Mapping[str, object]:
    response = admin_status()
    return json.loads(response.body.decode("utf-8"))


def _fetch_metrics() -> str:
    response = admin_metrics()
    return response.body.decode("utf-8")


METRIC_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][^ {]*)(?:\{(?P<labels>[^}]*)\})?\s+(?P<value>[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)$"
)


def _parse_labels(raw: str) -> Tuple[Tuple[str, str], ...]:
    labels: List[Tuple[str, str]] = []
    for part in raw.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        labels.append((key.strip(), value.strip('"')))
    return tuple(sorted(labels))


def _parse_metrics(text: str) -> Dict[str, Dict[Tuple[Tuple[str, str], ...], float]]:
    metrics: Dict[str, Dict[Tuple[Tuple[str, str], ...], float]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = METRIC_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        label_group = match.group("labels")
        labels = _parse_labels(label_group) if label_group else tuple()
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        metrics.setdefault(name, {})[labels] = value
    return metrics


def _metric_value(metrics: Mapping[str, Dict[Tuple[Tuple[str, str], ...], float]], name: str) -> float:
    entries = metrics.get(name, {})
    if not entries:
        return 0.0
    # Return the first recorded value (histograms expose aggregate counters)
    return next(iter(entries.values()))


def _metrics_summary(text: str) -> Dict[str, object]:
    metrics = _parse_metrics(text)
    sparklines = {
        "reflexion_latency_ms_max": _metric_value(metrics, "sos_reflexion_latency_ms_max"),
        "critic_latency_ms_max": _metric_value(metrics, "sos_critic_latency_ms_max"),
        "oracle_latency_ms_max": _metric_value(metrics, "sos_oracle_latency_ms_max"),
        "hungryeyes_corpus_bytes": _metric_value(metrics, "sos_hungryeyes_corpus_bytes"),
    }
    counters = {
        "reflexion_rate_limited_total": _metric_value(metrics, "sos_reflexion_rate_limited_total"),
        "oracle_rate_limited_total": _metric_value(metrics, "sos_oracle_rate_limited_total"),
        "goals_rate_limited_total": _metric_value(metrics, "sos_goals_rate_limited_total"),
    }
    return {"sparklines": sparklines, "counters": counters}


def _rehearsal_runs() -> List[Path]:
    base = get_data_root() / "glow" / "rehearsal"
    if not base.exists():
        return []
    runs = [candidate for candidate in base.iterdir() if candidate.is_dir()]
    runs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return runs


def _resolve_latest_run() -> Tuple[Optional[Path], Optional[Path]]:
    runs = _rehearsal_runs()
    latest_link = get_data_root() / "glow" / "rehearsal" / "latest"
    latest: Optional[Path] = None
    if latest_link.exists():
        latest = latest_link.resolve()
    elif runs:
        latest = runs[0]
    previous = None
    for run in runs:
        if latest is None:
            break
        if run.resolve() != latest.resolve():
            previous = run
            break
    return latest, previous


def _load_file(path: Path, *, limit: int = 16000) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if len(content) > limit:
        return content[:limit] + "\n… (truncated)"
    return content


def _load_rehearsal_artifacts() -> Dict[str, object]:
    latest, previous = _resolve_latest_run()
    if latest is None:
        return {
            "latest": None,
            "previous": None,
            "report": "No rehearsal artifacts found.",
            "integrity": "",
            "diff": "",
        }
    report_path = latest / "REHEARSAL_REPORT.json"
    integrity_path = latest / "INTEGRITY_SUMMARY.json"
    report = _load_file(report_path)
    integrity = _load_file(integrity_path)
    diff = ""
    if previous is not None:
        prev_report = _load_file(previous / "REHEARSAL_REPORT.json")
        if report and prev_report:
            lines = list(
                _diff_text(prev_report, report, fromfile=previous.name, tofile=latest.name)
            )
            diff = "\n".join(lines)
    return {
        "latest": latest.name,
        "previous": previous.name if previous else None,
        "report": report,
        "integrity": integrity,
        "diff": diff,
    }


def _diff_text(before: str, after: str, *, fromfile: str, tofile: str) -> Iterable[str]:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    for line in difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
        n=10,
    ):
        yield line


def _load_events(limit: int = 30) -> List[Dict[str, str]]:
    latest, _previous = _resolve_latest_run()
    if latest is None:
        return []
    log_path = latest / "logs" / "runtime.jsonl"
    if not log_path.exists():
        return []
    lines: deque[str] = deque(maxlen=limit)
    try:
        with log_path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if raw:
                    lines.append(raw)
    except OSError:
        return []
    events: List[Dict[str, str]] = []
    for raw in lines:
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        events.append(
            {
                "ts": entry.get("ts", ""),
                "summary": _summarise_event(entry),
            }
        )
    return list(reversed(events))


def _summarise_event(entry: Mapping[str, object]) -> str:
    if "event" in entry:
        event = str(entry["event"])
    elif "council" in entry:
        event = f"council:{entry['council'].get('outcome', 'unknown')}"
    else:
        event = "log"
    detail = entry.get("message") or entry.get("note") or ""
    if isinstance(detail, Mapping):
        detail = json.dumps(detail)
    if detail:
        return f"{event} – {detail}"
    return event


def _status_payload() -> Dict[str, object]:
    status = _fetch_status()
    metrics_text = _fetch_metrics()
    metrics = _metrics_summary(metrics_text)
    artifacts = _load_rehearsal_artifacts()
    events = _load_events()
    return {
        "retrieved_at": datetime.utcnow().isoformat() + "Z",
        "overall": status.get("overall"),
        "modules": status.get("modules", {}),
        "metrics": metrics,
        "events": events,
        "artifacts": artifacts,
    }


def _silhouette_recent_payload(limit: int) -> Dict[str, object]:
    silhouettes = load_recent_silhouettes(limit)
    return {
        "source": "embodiment_silhouette",
        "count": len(silhouettes),
        "silhouettes": silhouettes,
    }


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(_DASHBOARD_HTML)


@app.get("/operator/silhouettes", response_class=HTMLResponse)
async def operator_silhouettes() -> HTMLResponse:
    return HTMLResponse(_SILHOUETTES_HTML)


@app.get("/data/status", response_class=JSONResponse)
async def dashboard_data(_: None = Depends(require_token)) -> JSONResponse:
    return JSONResponse(_status_payload())


@app.get("/api/silhouettes/recent", response_class=JSONResponse)
async def silhouettes_recent(
    n: int = 7,
    _: None = Depends(require_token),
) -> JSONResponse:
    if n <= 0:
        return JSONResponse({"source": "embodiment_silhouette", "count": 0, "silhouettes": []})
    limit = min(n, 60)
    return JSONResponse(_silhouette_recent_payload(limit))


@app.get("/api/silhouettes/{date_value}", response_class=JSONResponse)
async def silhouettes_by_date(
    date_value: str,
    _: None = Depends(require_token),
) -> JSONResponse:
    try:
        payload = load_silhouette(date_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload is None:
        raise HTTPException(status_code=404, detail="silhouette not found")
    return JSONResponse(payload)


_SILHOUETTES_HTML = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <title>Embodiment Silhouettes</title>
    <style>
      body { font-family: "Inter", "Segoe UI", sans-serif; background:#0f172a; color:#e2e8f0; margin:0; }
      header { padding:1.5rem 2rem; background:#1e293b; display:flex; justify-content:space-between; align-items:center; }
      header h1 { margin:0; font-size:1.5rem; }
      header a { color:#38bdf8; text-decoration:none; font-size:0.9rem; }
      main { padding:2rem; }
      section { background:#1e293b; border-radius:0.75rem; padding:1.5rem; box-shadow:0 4px 10px rgba(15,23,42,0.6); }
      .controls { display:flex; align-items:center; gap:1rem; margin-bottom:1rem; }
      .controls button { background:#38bdf8; border:none; color:#0f172a; padding:0.5rem 0.9rem; border-radius:0.45rem; font-weight:600; cursor:pointer; }
      .controls span { font-size:0.85rem; color:#94a3b8; }
      .grid-header, summary.row { display:grid; grid-template-columns: 130px 1.6fr 1.4fr 1.6fr; gap:1rem; align-items:center; }
      .grid-header { font-size:0.75rem; text-transform:uppercase; color:#94a3b8; padding:0 0.25rem 0.5rem; }
      details.silhouette { background:#0f172a; border-radius:0.6rem; border:1px solid rgba(148,163,184,0.2); margin-bottom:0.75rem; }
      details.silhouette summary { list-style:none; cursor:pointer; padding:0.75rem 1rem; font-weight:600; }
      details.silhouette summary::-webkit-details-marker { display:none; }
      details.silhouette summary span { font-weight:500; color:#e2e8f0; }
      details.silhouette summary span.label { color:#f8fafc; font-weight:600; }
      details.silhouette pre { margin:0; padding:0.9rem 1rem 1.1rem; color:#cbd5f5; background:#0b1220; border-top:1px solid rgba(148,163,184,0.15); max-height:320px; overflow:auto; }
      #empty-state { color:#94a3b8; font-size:0.9rem; }
    </style>
  </head>
  <body>
    <header>
      <h1>Embodiment Silhouettes</h1>
      <a href=\"/\">Back to dashboard</a>
    </header>
    <main>
      <section>
        <div class=\"controls\">
          <button id=\"refresh\">Refresh</button>
          <span id=\"status\">Awaiting data...</span>
        </div>
        <div class=\"grid-header\">
          <div>Date</div>
          <div>Top postures</div>
          <div>Plugin usage totals</div>
          <div>Anomaly summary</div>
        </div>
        <div id=\"silhouette-list\"></div>
        <div id=\"empty-state\" hidden>No silhouettes found in glow/silhouettes.</div>
      </section>
    </main>
    <script>
      let dashboardToken = sessionStorage.getItem('sos_dashboard_token') || '';

      function promptToken() {
        const token = window.prompt('Enter dashboard token');
        if (token) {
          dashboardToken = token.trim();
          sessionStorage.setItem('sos_dashboard_token', dashboardToken);
        }
      }

      function summarizeCounts(counts, limit) {
        if (!counts) return '—';
        const entries = Object.entries(counts).map(([key, value]) => [key, Number(value) || 0]);
        if (!entries.length) return '—';
        entries.sort((a, b) => b[1] - a[1]);
        return entries.slice(0, limit).map(([key, value]) => `${key} (${value})`).join(', ');
      }

      function pluginSummary(usage) {
        const entries = Object.entries(usage || {}).map(([key, value]) => [key, Number(value) || 0]);
        const total = entries.reduce((acc, [, value]) => acc + value, 0);
        if (!entries.length) return '0 total';
        entries.sort((a, b) => b[1] - a[1]);
        const top = entries.slice(0, 3).map(([key, value]) => `${key} (${value})`).join(', ');
        return `${total} total · ${top}`;
      }

      function anomalySummary(anomalies) {
        const counts = (anomalies && anomalies.severity_counts) ? anomalies.severity_counts : {};
        const low = Number(counts.low) || 0;
        const moderate = Number(counts.moderate) || 0;
        const critical = Number(counts.critical) || 0;
        let summary = `low ${low} · mod ${moderate} · crit ${critical}`;
        if (anomalies && anomalies.latest_anomaly) {
          const latest = anomalies.latest_anomaly;
          summary += ` · latest ${latest.severity || 'unknown'} ${latest.channel || 'unknown'} @${latest.timestamp || '?'}`;
        }
        return summary;
      }

      function renderSilhouettes(payload) {
        const list = document.getElementById('silhouette-list');
        const empty = document.getElementById('empty-state');
        list.innerHTML = '';
        const items = (payload && payload.silhouettes) ? payload.silhouettes : [];
        if (!items.length) {
          empty.hidden = false;
          return;
        }
        empty.hidden = true;
        items.forEach(entry => {
          const details = document.createElement('details');
          details.className = 'silhouette';
          const summary = document.createElement('summary');
          summary.className = 'row';
          const date = entry.date || 'unknown';
          const postures = summarizeCounts(entry.posture_counts || {}, 3);
          const plugins = pluginSummary(entry.plugin_usage || {});
          const anomalies = anomalySummary(entry.anomalies || {});
          summary.innerHTML = `
            <span class=\"label\">${date}</span>
            <span>${postures || '—'}</span>
            <span>${plugins || '—'}</span>
            <span>${anomalies || '—'}</span>
          `;
          const pre = document.createElement('pre');
          pre.textContent = JSON.stringify(entry, null, 2);
          details.appendChild(summary);
          details.appendChild(pre);
          list.appendChild(details);
        });
      }

      async function fetchSilhouettes() {
        if (!dashboardToken) {
          promptToken();
        }
        const headers = dashboardToken ? { 'Authorization': `Bearer ${dashboardToken}` } : {};
        const status = document.getElementById('status');
        status.textContent = 'Loading silhouettes...';
        try {
          const response = await fetch('/api/silhouettes/recent?n=30', { headers, cache: 'no-store' });
          if (response.status === 401 || response.status === 403) {
            sessionStorage.removeItem('sos_dashboard_token');
            dashboardToken = '';
            status.textContent = 'Token required.';
            promptToken();
            return;
          }
          const payload = await response.json();
          renderSilhouettes(payload);
          status.textContent = `Loaded ${payload.count || 0} silhouettes.`;
        } catch (error) {
          console.error('Silhouette fetch failed', error);
          status.textContent = 'Failed to load silhouettes.';
        }
      }

      document.getElementById('refresh').addEventListener('click', fetchSilhouettes);
      fetchSilhouettes();
    </script>
  </body>
</html>
"""


_DASHBOARD_HTML = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <title>SentientOS Operator Dashboard</title>
    <style>
      body { font-family: "Inter", "Segoe UI", sans-serif; background:#0f172a; color:#e2e8f0; margin:0; }
      header { padding:1.5rem 2rem; background:#1e293b; box-shadow:0 2px 4px rgba(15,23,42,0.4); }
      h1 { margin:0; font-size:1.6rem; }
      main { padding:2rem; display:grid; gap:1.5rem; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
      section { background:#1e293b; border-radius:0.75rem; padding:1.5rem; box-shadow:0 4px 10px rgba(15,23,42,0.6); }
      section h2 { margin-top:0; font-size:1.1rem; letter-spacing:0.02em; text-transform:uppercase; color:#94a3b8; }
      #health-panels { display:grid; gap:0.75rem; }
      .panel { background:#0f172a; border-radius:0.5rem; padding:0.75rem 1rem; border:1px solid rgba(148,163,184,0.2); }
      .panel h3 { margin:0 0 0.3rem 0; font-size:1rem; text-transform:capitalize; }
      .panel .status { font-weight:600; }
      .panel pre { margin:0.5rem 0 0; max-height:140px; overflow:auto; background:rgba(15,23,42,0.7); padding:0.5rem; border-radius:0.4rem; }
      ul#events { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:0.6rem; max-height:280px; overflow:auto; }
      ul#events li { background:#0f172a; padding:0.65rem 0.75rem; border-radius:0.5rem; border:1px solid rgba(148,163,184,0.15); }
      ul#events li span.time { display:block; font-size:0.75rem; color:#94a3b8; }
      .artifacts details { margin-bottom:0.75rem; }
      .artifacts summary { cursor:pointer; font-weight:600; }
      .artifacts pre { max-height:240px; overflow:auto; background:#0f172a; padding:0.75rem; border-radius:0.5rem; border:1px solid rgba(148,163,184,0.2); }
      .sparklines { display:grid; gap:1rem; }
      .spark { background:#0f172a; border-radius:0.5rem; padding:0.75rem 1rem; border:1px solid rgba(148,163,184,0.15); }
      .spark-header { display:flex; justify-content:space-between; align-items:center; font-size:0.9rem; color:#cbd5f5; margin-bottom:0.5rem; }
      canvas { width:100%; height:60px; }
      .rate-limits { margin-top:1rem; font-size:0.85rem; color:#94a3b8; }
      .rate-limits span { display:block; margin-bottom:0.25rem; }
      footer { padding:1rem 2rem; font-size:0.75rem; color:#64748b; text-align:right; }
    </style>
  </head>
  <body>
    <header>
      <h1>SentientOS Operator Dashboard</h1>
    </header>
    <main>
      <section>
        <h2>Live Health</h2>
        <div id=\"health-panels\"></div>
      </section>
      <section>
        <h2>Events Feed</h2>
        <ul id=\"events\"></ul>
      </section>
      <section class=\"artifacts\">
        <h2>Rehearsal Artifacts</h2>
        <div id=\"artifact-meta\" class=\"meta\"></div>
        <details open>
          <summary>Latest report.json</summary>
          <pre id=\"artifact-report\"></pre>
        </details>
        <details>
          <summary>Latest integrity.json</summary>
          <pre id=\"artifact-integrity\"></pre>
        </details>
        <details>
          <summary>Diff vs previous run</summary>
          <pre id=\"artifact-diff\"></pre>
        </details>
      </section>
      <section>
        <h2>Metrics Sparklines</h2>
        <div class=\"sparklines\">
          <div class=\"spark\" data-metric=\"reflexion_latency_ms_max\">
            <div class=\"spark-header\">
              <span>Reflexion latency (max ms)</span>
              <span class=\"spark-value\" data-value=\"reflexion_latency_ms_max\">0</span>
            </div>
            <canvas width=\"280\" height=\"60\"></canvas>
          </div>
          <div class=\"spark\" data-metric=\"critic_latency_ms_max\">
            <div class=\"spark-header\">
              <span>Critic latency (max ms)</span>
              <span class=\"spark-value\" data-value=\"critic_latency_ms_max\">0</span>
            </div>
            <canvas width=\"280\" height=\"60\"></canvas>
          </div>
          <div class=\"spark\" data-metric=\"oracle_latency_ms_max\">
            <div class=\"spark-header\">
              <span>Oracle latency (max ms)</span>
              <span class=\"spark-value\" data-value=\"oracle_latency_ms_max\">0</span>
            </div>
            <canvas width=\"280\" height=\"60\"></canvas>
          </div>
          <div class=\"spark\" data-metric=\"hungryeyes_corpus_bytes\">
            <div class=\"spark-header\">
              <span>HungryEyes corpus (bytes)</span>
              <span class=\"spark-value\" data-value=\"hungryeyes_corpus_bytes\">0</span>
            </div>
            <canvas width=\"280\" height=\"60\"></canvas>
          </div>
        </div>
        <div class=\"rate-limits\">
          <span>Reflexion rate limited: <strong id=\"reflexion-rate\">0</strong></span>
          <span>Oracle rate limited: <strong id=\"oracle-rate\">0</strong></span>
          <span>Goals rate limited: <strong id=\"goals-rate\">0</strong></span>
        </div>
      </section>
    </main>
    <footer>Data sourced from /admin/status and /admin/metrics</footer>
    <script>
      const metricHistory = {};
      const maxPoints = 40;
      let dashboardToken = sessionStorage.getItem('sos_dashboard_token') || '';

      function promptToken() {
        const token = window.prompt('Enter dashboard token');
        if (token) {
          dashboardToken = token.trim();
          sessionStorage.setItem('sos_dashboard_token', dashboardToken);
        }
      }

      async function fetchStatus() {
        if (!dashboardToken) {
          promptToken();
        }
        const headers = dashboardToken ? { 'Authorization': `Bearer ${dashboardToken}` } : {};
        try {
          const response = await fetch('/data/status', { headers, cache: 'no-store' });
          if (response.status === 401 || response.status === 403) {
            sessionStorage.removeItem('sos_dashboard_token');
            dashboardToken = '';
            promptToken();
            return;
          }
          const payload = await response.json();
          renderHealth(payload.modules);
          renderEvents(payload.events);
          renderArtifacts(payload.artifacts);
          renderMetrics(payload.metrics);
        } catch (error) {
          console.error('Dashboard refresh failed', error);
        }
      }

      function renderHealth(modules) {
        const container = document.getElementById('health-panels');
        container.innerHTML = '';
        Object.entries(modules || {}).forEach(([name, info]) => {
          const panel = document.createElement('div');
          panel.className = 'panel';
          const status = (info && info.status) ? info.status : 'unknown';
          panel.innerHTML = `<h3>${name.replace(/_/g, ' ')}</h3><div class="status">${status}</div>`;
          const meta = document.createElement('pre');
          meta.textContent = JSON.stringify(info, null, 2);
          panel.appendChild(meta);
          container.appendChild(panel);
        });
      }

      function renderEvents(events) {
        const list = document.getElementById('events');
        list.innerHTML = '';
        (events || []).forEach(event => {
          const item = document.createElement('li');
          const ts = document.createElement('span');
          ts.className = 'time';
          ts.textContent = event.ts || '';
          const text = document.createElement('div');
          text.textContent = event.summary || '';
          item.appendChild(ts);
          item.appendChild(text);
          list.appendChild(item);
        });
      }

      function renderArtifacts(artifacts) {
        document.getElementById('artifact-report').textContent = artifacts.report || '';
        document.getElementById('artifact-integrity').textContent = artifacts.integrity || '';
        document.getElementById('artifact-diff').textContent = artifacts.diff || 'No previous run diff available.';
        const meta = document.getElementById('artifact-meta');
        const latest = artifacts.latest ? `latest run: ${artifacts.latest}` : 'no runs yet';
        const previous = artifacts.previous ? `previous: ${artifacts.previous}` : 'previous: n/a';
        meta.textContent = `${latest} — ${previous}`;
      }

      function renderMetrics(metrics) {
        const sparklines = metrics && metrics.sparklines ? metrics.sparklines : {};
        Object.entries(sparklines).forEach(([name, value]) => {
          metricHistory[name] = metricHistory[name] || [];
          const series = metricHistory[name];
          series.push(Number(value) || 0);
          if (series.length > maxPoints) {
            series.shift();
          }
          const container = document.querySelector(`.spark[data-metric="${name}"]`);
          if (!container) return;
          const canvas = container.querySelector('canvas');
          const ctx = canvas.getContext('2d');
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          const values = series.length ? series : [0];
          const maxValue = Math.max(...values, 1);
          const step = canvas.width / Math.max(values.length - 1, 1);
          ctx.strokeStyle = '#38bdf8';
          ctx.lineWidth = 2;
          ctx.beginPath();
          values.forEach((val, idx) => {
            const x = idx * step;
            const y = canvas.height - (val / maxValue) * canvas.height;
            if (idx === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          });
          ctx.stroke();
          const label = container.querySelector(`[data-value="${name}"]`);
          if (label) {
            label.textContent = (Number(value) || 0).toFixed(2);
          }
        });
        const counters = metrics && metrics.counters ? metrics.counters : {};
        document.getElementById('reflexion-rate').textContent = counters.reflexion_rate_limited_total || 0;
        document.getElementById('oracle-rate').textContent = counters.oracle_rate_limited_total || 0;
        document.getElementById('goals-rate').textContent = counters.goals_rate_limited_total || 0;
      }

      fetchStatus();
      setInterval(fetchStatus, 5000);
    </script>
  </body>
</html>
"""


__all__ = ["app"]
