# Cross-Host Replay Provenance

This document explains how replay verification is integrated into WAN truth reconciliation.

## Replay flow

When `--emit-replay` is set for a WAN lab run:

1. each node runs replay verification (`forge_replay --verify`),
2. latest replay artifact path is captured per node,
3. replay status is consumed by `replay_truth`,
4. replay evidence is included in `provenance_reconciliation.json`.

## Runtime vs replay distinction

A cluster can look runtime-healthy but still fail replay/provenance checks.

The truth layer marks this explicitly by:

- classifying `replay_truth` independently,
- issuing contradictions when runtime health and replay truth diverge,
- producing a final truth digest that includes both runtime and replay evidence.

## Re-anchor continuity

Re-anchor scenarios are checked for:

- `broken_preserved` visibility,
- explicit checkpoint ids,
- continuation descending from anchor,
- cluster-level behavior around the re-anchored node.

These are surfaced under `reanchor_truth` and provenance node correlations.

## Artifacts

`wan_truth/` includes:

- `truth_oracle_summary.json`
- `truth_dimensions.json`
- `provenance_reconciliation.json`
- `evidence_manifest.json`
- `contradictions_report.json`
- `cluster_final_truth_digest.json`
