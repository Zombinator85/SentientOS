# System Constitution Surface (Capstone)

## Purpose

SentientOS now composes a single canonical constitutional surface at:

- `glow/constitution/system_constitution.json`

This artifact answers, deterministically and in one place:

- active constitution/manifest identity
- active invariant surface
- audit trust and re-anchor posture
- pulse trust epoch posture
- effective runtime posture and governor restriction/action classes
- active degraded/restricted modes
- federation governance/quorum/trust-ledger posture
- constitutional digest and artifact dependency paths

## Composition model

The surface is **compositional**, not duplicative. It reads existing sources of truth from `vow/` and `glow/` artifacts and creates a bounded projection:

- `vow/immutable_manifest.json`
- `vow/invariants.yaml`
- `glow/runtime/audit_trust_state.json`
- `glow/governor/rollup.json`, `storm_budget.json`, `observability.jsonl`
- `glow/pulse_trust/epoch_state.json`
- `glow/federation/governance_digest.json`, `federation_quorum_policy.json`, `peer_governance_digests.json`, `trust_ledger_state.json`

A top-level `constitutional_digest` is SHA-256 over canonical JSON of the composed constitutional core.

## Operator surfaces

Constitution outputs:

- `glow/constitution/system_constitution.json`
- `glow/constitution/constitution_summary.json`
- `glow/constitution/constitution_transitions.jsonl`

CLI:

- `python scripts/system_constitution.py --json`
- `python scripts/system_constitution.py --latest`
- `python scripts/system_constitution.py --verify`

Exit codes:

- `0` healthy and fully composed
- `1` degraded but coherent/composable
- `2` restricted (e.g., degraded audit trust / restricted posture / compromise response)
- `3` missing required constitutional anchors/artifacts

`forge_status` now includes constitution summary references so operators can view posture without opening constitution artifacts directly.

## Current constitutional blind spots

Still intentionally outside this canonical surface (for now):

- full per-event replay proof linkage to constitution digest at event time
- richer cycle-boundary evidence inclusion beyond existing rollups
- deep semantic invariant runtime evaluation traces (only invariant surface summary is included)

These remain available in their original artifacts and can be joined by tooling without introducing parallel state.
