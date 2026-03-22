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

## Contract-status consumer semantics

`fleet_health_dashboard.json` now carries `contract_drift_rollup.contract_rows` copied
from `latest_pointers.surfaces.contract_status.metadata.summary_rows`, so operators get
the same contract rendering semantics in observatory views and ops CLI surface
selection:

- freshness/completeness (`pointer_state`, `freshness_posture`)
- domain posture (`status`, `drift_posture`)
- policy/gate context (`policy_meaning`, `gate_meaning`)
- reason/provenance (`summary_reason`, `primary_artifact_path`, `created_at`)

This keeps stale-vs-drift and baseline-missing-vs-drifted distinct in one row:

- `stale + healthy` => freshness issue, not domain drift
- `current + drifted` => contract drift issue
- `current + baseline_missing` => baseline absent/precondition issue
- `missing + indeterminate` => evidence unavailable

`fleet_health_dashboard.json` and `fleet_health_summary.json` also expose compact
contract alert badges derived from those same normalized rows (not re-derived ad hoc):

- `contract_alert_badge` and `contract_alert_reason` in dashboard rollups
- `contract_row_summary.alert_counts` in summary and dashboard payloads
- `selected_surface=fleet_observatory` summary rows include:
  - `contract_alert_counts`
  - `contract_alert_badge`
  - `contract_alert_reason`
  - `contract_stale_or_missing_rows`
  - `contract_drifted_rows`
  - `contract_baseline_missing_rows`
  - `contract_indeterminate_rows`

Badge priority is deterministic:

1. `domain_drift`
2. `baseline_absent`
3. `freshness_issue`
4. `partial_evidence`
5. `informational`

Out of scope for this layer:

- changing protected-corridor blocking doctrine
- changing contract drift policy
- rewriting source `contract_status.json` or latest-pointer architecture
