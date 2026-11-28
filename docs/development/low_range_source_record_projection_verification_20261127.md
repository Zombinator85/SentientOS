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

The unexecuted v15 condition-bound source plan was marked superseded_before_execution. Source plan v16 was superseded after Ollama rejected its friendly model alias before inference. Source plan v17 uses the exact registered Ollama name for the same pinned artifact, binds the updated implementation, keeps the empty-history boundary, and reserves fresh source cycle IDs and seeds. Its offline verify-plan check passed with inference disabled. Seed roster v4 points to source plan v17 and keeps the held-out wide-range target behind the existing eligibility gate. The v16 failure artifact records no model inference.


## Held-out transfer prompt budget diagnosis

The v4 held-out wide-range cycle stopped before transfer inference because its owner preview selected the two low-range anchor records but omitted the current wide-range acquisition record. The exact failure prompt used 22,748 characters under a 24,576-character cap. CPU-only reconstruction measured compact score-bound packets at 3,360 characters for the acquisition record and 3,549 and 3,390 for the two source anchors. The corresponding three-record prompt is estimated at about 26,108 characters before identity-binding variation, so the prior cap could not retain all three.

The runner cap is now 28,672 characters. A CPU-only planned preflight and actual resident-owner preview were then run against the retained cycle-21 history. The planner produced a 26,417-character prompt; the resident owner bound present and restored prompts at 26,618 characters and the withheld control at 13,931. Present and restored each contained the exact same three record IDs and digests: the current wide-range acquisition record and both low-range source anchors. All prompts were within the revised character cap. The configured 8,192-token context was unchanged; this CPU preview does not measure tokenizer consumption. The owner-to-binder path was exercised with inference disabled; no learning or authority was established. The isolated diagnostic plan and reports are under `sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-owner-prompt-budget-cpu-replay-v2/` (plan digest `e09eb1fe9a11679ea3e271fa8c04e8a22abc72e475c392a980f4433721044239`; owner-preview audit digest `520e17193ac73c3285bb37ca53fb9d52d99342861cc047bb33a9535b631e7ecd`). They are diagnostic-only, not an executable replacement for the failed target plan.
