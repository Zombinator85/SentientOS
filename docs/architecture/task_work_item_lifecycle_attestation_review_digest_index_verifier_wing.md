# Task Wing: Work Item Lifecycle Attestation Review Digest Index Verifier

This wing verifies a **supplied** lifecycle attestation review digest index using metadata-only evidence.

## Boundaries
- Verification-only, no index generation.
- No lifecycle/action/orchestration invocation.
- No workspace/branch/PR mutation.
- No provider/network/shell authority expansion.

## Inputs
- Required review digest index JSON.
- Optional source review digests.
- Optional review digest verifier reports.
- Optional matrix report.

## Outputs
- Deterministic verification report metadata.
- Optional explicit output artifact only when requested.

## CLI
`python scripts/verify_work_item_lifecycle_attestation_review_digest_index.py --review-digest-index <index.json> --summary`
