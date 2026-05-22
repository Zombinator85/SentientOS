# Work Item Lifecycle Attestation Review Digest Verifier Wing

This wing verifies lifecycle attestation review digest metadata against supplied lifecycle attestation index and index verification report evidence.

It is metadata-only verification and does not invoke lifecycle actions.

CLI:

`python scripts/verify_work_item_lifecycle_attestation_review_digest.py --review-digest <digest.json> --attestation-index <index.json> --index-verification <verification.json> --summary`
