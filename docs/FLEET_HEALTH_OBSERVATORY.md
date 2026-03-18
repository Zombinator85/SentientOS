# Fleet Health Observatory

The Fleet Health Observatory is a deterministic aggregation layer that summarizes existing SentientOS health and validation artifacts into a single operator-facing surface.

## What it aggregates

The observatory reads source artifacts and does not replace them:

- `glow/contracts/contract_status.json`
- `glow/contracts/protected_corridor_report.json`
- `glow/simulation/baseline_report.json`
- `glow/formal/formal_check_summary.json`
- WAN truth/oracle outputs from latest `glow/lab/wan/<run_id>/run_summary.json`
- WAN release gate outputs in `glow/lab/wan_gate/wan_gate_report.json`
- Remote preflight trend outputs in `glow/lab/remote_preflight/remote_preflight_trend_report.json`
- Incident bundle rollup from `glow/incidents/bundle_*.json`

## Fleet-health dimensions

The observatory emits bounded statuses for:

- `constitution_health`
- `corridor_health`
- `simulation_health`
- `formal_health`
- `federation_health`
- `wan_gate_health`
- `remote_smoke_health`
- `preflight_drift_health`
- `evidence_density_health`
- `release_readiness`

Statuses are deterministic and bounded to:

- `healthy`
- `degraded`
- `restricted`
- `warning`
- `blocking`
- `missing_evidence`
- `unavailable`

## Generated artifacts

The observatory writes to `glow/observatory/`:

- `fleet_health_summary.json`
- `fleet_health_dashboard.json`
- `fleet_degradations.json`
- `fleet_release_readiness.json`
- `fleet_observatory_manifest.json`
- `final_fleet_health_digest.json`
- `fleet_health_history.jsonl` (bounded append-only history)

## Operator command path

Use the existing ops CLI:

- `python -m sentientos.ops observatory fleet --json`
- `python -m sentientos.ops observatory fleet --dashboard`
- `python -m sentientos.ops observatory fleet --release-readiness`
- `python -m sentientos.ops observatory fleet --degradations`

## Triage model

1. Read `fleet_health_summary.json` for top-level status and release-readiness.
2. Read `fleet_degradations.json` for prioritized blockers/degradations.
3. Drill into source artifacts using `fleet_observatory_manifest.json`.

The observatory is a control-plane summary layer, not a source-of-truth replacement.
