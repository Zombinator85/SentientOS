# SentientOS Operator Dashboard

The operator dashboard provides a read-only view into the rehearsal subsystem so on-call guardians can assess module health in a
single glance. It is implemented as a lightweight FastAPI + HTMX-lite experience and only reads from the existing `/admin/status`
and `/admin/metrics` endpoints plus the `glow/` rehearsal artifacts.

## Launching

1. Export a bearer token for local sessions:

   ```bash
   export SENTIENTOS_DASHBOARD_TOKEN="super-secret-token"
   ```

2. Run the ASGI app using Uvicorn (or any compatible server):

   ```bash
   uvicorn apps.dashboard.main:app --reload --port 8001
   ```

3. Open the dashboard and paste the bearer token when prompted.

   ```bash
   open http://localhost:8001/
   ```

The root HTML shell renders without data until the correct bearer token is supplied. All AJAX calls use the provided token and no
write paths are ever exposed.

## Panels

### Live Health

- Mirrors the payload from `/admin/status`.
- Each module card surfaces `status`, budget counters, and any recent rate-limit timestamps.
- Cards render degraded or limited modules in-line so the on-call can triage without digging through JSON files.

### Events Feed

- Streams the tail of `glow/rehearsal/latest/logs/runtime.jsonl`.
- Highlights critic disagreements, council tie-break decisions, and quarantine notifications.
- The list auto-refreshes every five seconds while staying capped to the most recent 30 entries.

### Rehearsal Artifacts

- Surfaces `REHEARSAL_REPORT.json` and `INTEGRITY_SUMMARY.json` from the latest rehearsal.
- Provides a unified diff between the latest report and the immediately previous run.
- Annotates which run is currently linked to `glow/rehearsal/latest` for provenance tracking.

### Metrics Sparklines

- Renders client-side sparklines for reflexion, critic, and oracle latencies plus HungryEyes corpus size.
- Tracks rate-limit counters for reflexion, oracle, and goal curator budgets.
- All metrics data is sourced exclusively from `/admin/metrics` without any additional storage.

### SLO Overview

- Displays the current values and targets for every SLO defined in `config.slos.yaml`.
- Cards flip between green/yellow/red states based on whether the SLO is currently satisfied, trending near a breach, or broken.
- Each entry links directly to the raw JSON payload from `/admin/status` for auditability.

### Quick Links & Redaction Preview

- The right-hand sidebar links to the latest rehearsal, performance smoke summary, and integrity reports under `glow/`.
- A development-only toggle renders the log redactor preview so operators can confirm that bearer tokens and emails are masked before forwarding logs.

## Troubleshooting

- **401 / 403 responses** – ensure the `Authorization: Bearer <token>` header is set for all API requests.
- **Empty artifacts** – run `make rehearse` to regenerate the `glow/rehearsal/latest` directory.
- **No events** – confirm runtime logs are stored under `glow/rehearsal/latest/logs/runtime.jsonl` and the process has read
  access.
