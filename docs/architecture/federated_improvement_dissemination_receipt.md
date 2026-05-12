# Federated Improvement Dissemination Receipt

`FederatedImprovementDisseminationReceipt` is a metadata-only, bounded artifact that records whether a node may **catalog or announce** improvement evidence to peers.

It is intentionally **not** transport, delivery, upload, network egress, subscription, sync, adoption, merge, conflict resolution, install/apply, production execution, or remote execution.

## Purpose

The receipt provides deterministic evidence posture for:

- original `FederatedImprovementCandidate` metadata
- optional local variant metadata
- optional lineage comparison metadata
- optional intake/rehearsal/review/readiness references

All references are identifiers and digests only, preserving peer sovereignty and local governance.

## Safety posture

Validation fails closed if required identities/digests/labels/scope/lineage refs are missing, if required gates are not accepted for ready claims, or if any forbidden transport/adoption/provider/secret/raw-payload/governance-bypass markers are present.

The artifact requires explicit booleans proving:

- metadata-only
- dissemination-catalog-only
- evidence-announcement-only
- no transport or sync performed
- no adoption/merge/apply/install/execute
- no production/remote execution
- no provider/network/export/prompt/runtime authority
- no secret/endpoint/client material
