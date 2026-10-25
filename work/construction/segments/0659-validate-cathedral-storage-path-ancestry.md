# Sequence 659: Validate Cathedral storage path ancestry

Review found that `AmendmentApplicator` created configured config, ledger, and rollback directories before verifying their resolved paths. The bounded fix resolves each target beneath the canonical runtime root and requires component-aware ancestry before the constructor creates any directories. External paths, traversal, and symlink escapes raise the stable `cathedral_storage_path_outside_base` error before filesystem effects. Valid in-root relative overrides remain supported.

Tests cover all three external overrides, a symlinked ledger path that resolves outside, and successful config, ledger, and rollback persistence under the runtime root.

The canonical regression suite passed 153 tests, skipped 16, and had zero failures in run `afd175ad615e40309341d9c8c9677815`; provenance SHA-256 `c8646b9acb9ce69cfb974a2d743c0d8195e4207332f3a8ab1be2f28a5fc30ad7`. Exact task acceptance is ready for all three required nodes. Targeted mypy and diff checks passed. Documentation dependencies were available and the build generated 616 pages. Custody verified all 658 preceding segments.

This is a locally validated, uncommitted construction candidate. No PR or hosted result is implied by this record. Candidate source file hashes are recorded in the evidence JSON.

Evidence: `work/construction/evidence/0659-validate-cathedral-storage-path-ancestry.json` (SHA-256 `6902cfece468c7f82b0b1e2c98c032019141b096fa349f2010e275ae7748d318`).
