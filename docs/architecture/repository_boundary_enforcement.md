# Repository Boundary Enforcement (Phase 33)

Boundary policy is encoded in `sentientos/system_closure/architecture_boundary_manifest.json`.

## Layer model
- `formal_core` and adjacent formal layers are authority-bearing and may not depend on symbolic/presentation modules.
- `expressive_apps`, `world_adapters`, and `dashboards_views` are consumer surfaces and must not import control-plane internals or private formal helpers.
- `orchestration_spine` remains the reference pattern: kernel authority, façade compatibility envelope, projection observational, adapters substrate helper only.

## Protected sinks
Direct writes to protected sinks (`logs/`, `glow/`, `audit_log/`, ledger/jsonl paths) are allowed only in modules listed under `protected_sinks.approved_direct_write_modules`.

## Known violations
Known violations are documented under `known_violations` with:
- `rule`
- `file`
- `detail`
- `severity`
- `remediation`

Tests fail on any new unlisted violation and also require known violations to stay explicit.

## Governance naming gate
Files containing `autonomous`, `agent`, `daemon`, or `scheduler` in their filename must either:
- live under an approved runtime/test path, or
- include a governance annotation marker (admission, consent/provenance, non-sovereignty, simulation constraints).
