# Work Item Lifecycle Attestation Review Digest Wing

This wing builds a deterministic, metadata-only reviewer digest from a lifecycle attestation index and its verification report.

## Boundaries
- No attestation index generation or verification invocation.
- No final attestation generation.
- No lifecycle closure/orchestration/action-wing execution.
- No workspace mutation, rollback, cleanup, network, provider, prompt, shell, or subprocess actions.

## CLI
`python scripts/build_work_item_lifecycle_attestation_review_digest.py --attestation-index <index.json> --index-verification <verification.json> --summary`
