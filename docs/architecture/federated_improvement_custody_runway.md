# Federated Improvement Custody Runway

This runway extends metadata-only federated improvement evidence after:

1. `FederatedImprovementCandidate`
2. `FederatedImprovementIntakeReceipt`

with four additional local-custody artifacts:

3. `FederatedImprovementRehearsalAuthorization`
4. `FederatedImprovementRehearsalResult`
5. `FederatedImprovementLocalReviewReceipt`
6. `FederatedImprovementAdoptionReadinessManifest`

## Boundaries

All runway artifacts are frozen metadata receipts/manifests with deterministic digests and fail-closed validation.

They **do not**:
- adopt, install, apply, merge, execute, schedule, route, or transport improvements,
- invoke providers or network/export runtime authority,
- include secrets/endpoints/clients,
- include prompt text, raw patches, or executable payloads.

## Custody progression

- **Rehearsal authorization:** classifies if local non-production rehearsal may occur.
- **Rehearsal result:** records rehearsal outcome metadata only.
- **Local review receipt:** records governance acceptance/rejection/hold for adoption-readiness consideration.
- **Adoption readiness manifest:** aggregates custody evidence and classifies readiness for a future separate adoption path.

Adoption is explicitly out-of-scope for this runway.
