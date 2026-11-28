# Low-range source record projection verification

Date: 2026-11-27

## Gap and change

Low-range source eligibility already bound the terminal writeback summary to the source run score and checked the inference receipts. It did not independently reconstruct the claimed score projection from the retained developmental-history record. The campaign verifier now reloads that manifest-bound record, checks its canonical serialization, record identity and digest/posture, and audits its candidate against the exact source run and task family. Eligibility requires one projectable experience, the matching source score digest and example/correct/incorrect/abstained counts, and zero unknown outcomes. The incorrect count is derived as probe count minus correct and abstained counts because the independent score schema does not store that field.

## CPU-only historical audit

Six completed rootless_integer_affine_transfer_low_range_v6 cycles were independently rechecked from their persisted record and raw source-run files. All six passed:

- record serialization, identity, and developmental-history record digest;
- source-run digest and independent score digest;
- recomputed projection source run ID, score digest, and all outcome counts;
- equality between the recomputed projection and the cycle report's declared projection.

This confirms the persisted evidence bridge for those six artifacts. It does not establish model attention, learning, causal attribution, or generalization.

## Preregistration lineage

The unexecuted v15 condition-bound source plan was marked superseded_before_execution. Source plan v16 binds the updated implementation, keeps the empty-history boundary and model artifact fixed, and reserves new source cycle IDs and seeds. Its offline verify-plan check passed with inference disabled. Seed roster v3 now points to source plan v16 and leaves the held-out wide-range target behind the existing eligibility gate. No target plan was materialized and no model was invoked.
