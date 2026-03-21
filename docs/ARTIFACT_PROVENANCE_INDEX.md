# Artifact Provenance Index

The artifact provenance index is a deterministic locator layer for major SentientOS artifact families.
It does **not** replace source truth artifacts. It provides:

- latest artifact pointers per major surface
- bounded pointer state (`current`, `superseded`, `missing`, `stale`, `unavailable`)
- digest-backed index artifacts for auditability
- cross-surface provenance links from summaries back to source artifacts

## Generated artifacts

Running `python -m sentientos.ops observatory artifacts --json` emits:

- `glow/observatory/artifact_index.json`
- `glow/observatory/latest_pointers.json`
- `glow/observatory/artifact_provenance_links.json`
- `glow/observatory/artifact_index_manifest.json`
- `glow/observatory/final_artifact_index_digest.json`
- `glow/observatory/artifact_index_history.jsonl` (bounded append-only history)

## Indexed surfaces (v1)

- `contract_status`
- `protected_corridor`
- `simulation_baseline`
- `formal_verification`
- `wan_gate`
- `wan_truth_oracle`
- `remote_preflight_trend`
- `fleet_observatory`
- `incident_summary`
- `run_tests_broad_lane`
- `mypy_broad_lane`
- `broad_lane_latest_summary`

## Latest selection

For each surface, selection uses a deterministic ordering chain:

1. `created_at` (or stable timestamp fallback)
2. `run_id` when present
3. lexicographic artifact path

The exact rule is recorded in each `latest_pointers.json` row under `latest_rule`.

## Pointer state semantics

- `current`: latest pointer exists and is within freshness window.
- `superseded`: artifact exists for surface but is not selected latest.
- `missing`: no artifact candidate for the surface.
- `stale`: latest exists but is older than the configured freshness window.
- `unavailable`: latest exists but timestamp metadata cannot be interpreted.

## Operator use

- All surfaces: `python -m sentientos.ops observatory artifacts --json`
- Latest pointers focus: `python -m sentientos.ops observatory artifacts --latest`
- Provenance links focus: `python -m sentientos.ops observatory artifacts --links`
- Single surface pointer: `python -m sentientos.ops observatory artifacts --surface wan_gate --json`

## Broad-lane selected-surface behavior

When the selected surface is `broad_lane_latest_summary`, `latest_pointers.json`
now includes `metadata.lane_rows` with normalized paired row semantics from the
aggregate broad-lane summary.

This means selected-surface readers can directly consume:

- `pointer_state` and `lane_state` together
- `policy_meaning` and `summary_reason`
- provenance pointers (`primary_artifact_path`, `supporting_artifact_paths`,
  `created_at`, `run_id`, `digest_sha256`)

without a second-hop reconstruction from per-lane pointer artifacts.
