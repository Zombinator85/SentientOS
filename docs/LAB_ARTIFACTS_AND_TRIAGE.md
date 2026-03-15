# Lab Artifacts and Triage

Each run is written under:

- `glow/lab/federation/<run_id>/`

Primary artifacts:

- `run_summary.json` (high-level status, oracle, observed outcomes)
- `run_metadata.json` (seed/scenario/node-count identity)
- `topology.json` (node identity/peer/port topology)
- `scenario_injection_log.jsonl` (fault timeline)
- `event_timeline.json` (coarse lifecycle events)
- `artifact_manifest.json` (file list + sha256 + size)
- per-node snapshots under `nodes/node-XX/glow/lab/`

## Correlation keys

Use these to correlate outcomes:

- `node_id` ↔ `peer_id`
- `node_id` ↔ `port`
- `node_id` ↔ runtime directory
- run-level `scenario` + `seed`
- injection type + target node

## Incident and replay surfaces

`--emit-bundle` triggers incident bundles and replay verification on each live node workspace so operator triage workflows are exercised during lab execution.
