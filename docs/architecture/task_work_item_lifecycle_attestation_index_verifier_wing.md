# Work Item Lifecycle Attestation Index Verifier Wing

This wing provides deterministic metadata-only verification for a lifecycle attestation index and optional source final attestation bundles.

It verifies:
- internal index coherence
- deterministic ordering
- duplicate/skipped counters against key lists
- attention-required flags against index entry signals
- optional source bundle digest/work-item alignment
- optional matrix status requirement

It never generates indices or attestation bundles, never performs lifecycle actions, and never mutates workspace content beyond optional explicit report output.

Primary surfaces:
- `sentientos/work_item_lifecycle_attestation_index_verifier.py`
- `scripts/verify_work_item_lifecycle_attestation_index.py`
- `tests/test_work_item_lifecycle_attestation_index_verifier.py`
- `tests/test_verify_work_item_lifecycle_attestation_index_script.py`
