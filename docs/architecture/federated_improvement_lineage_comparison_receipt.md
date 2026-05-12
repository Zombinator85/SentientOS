# Federated Improvement Lineage Comparison Receipt

`FederatedImprovementLineageComparisonReceipt` is a deterministic, metadata-only artifact for divergence inspection between:

- an original `FederatedImprovementCandidate`, and
- a local `FederatedImprovementLocalVariantArtifact`.

This receipt is **comparison-only**. It never performs adoption, merge, conflict resolution, install/apply, production execution, remote execution, transport, provider invocation, prompt assembly, or runtime authority expansion.

## Scope

The receipt classifies lineage on compact dimensions (identity, kind, digest, gates, compatibility/policy posture, risk, invariants, rehearsal, review) and emits a bounded status:

- `federated_improvement_lineage_comparison_compatible`
- `federated_improvement_lineage_comparison_compatible_with_conditions`
- `federated_improvement_lineage_comparison_incompatible`
- `federated_improvement_lineage_comparison_incomplete`
- `federated_improvement_lineage_comparison_contradicted`

## Safety posture

Validation is fail-closed and rejects missing lineage metadata, digest contradictions, unknown dimensions/statuses, governance bypass signals, and marker families related to adoption/execution/provider/network/export/prompt/runtime/secrets/raw patch or executable payload content.

Receiving nodes retain local governance and sovereignty; this artifact enables deterministic comparison without changing authority boundaries.
