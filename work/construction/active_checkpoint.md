# Active construction checkpoint

Sequence 151 preserves exact benchmark score provenance for task-family acquisitions. The World-State history-present score row carries its verified schema, evaluator identifier, plan/task digests, and invocation output digest. Writeback checks these against the public task descriptor and matching invocation, then retains the source metadata with the score. Examples bind to that score by digest without duplicating metadata. Generic non-family suite rows retain their previous compact form.

Task-family positive and adverse owner tests passed after the final binding checks. The generic partial-score suite passed with the family-only size restriction. Changed Python compiled; UTF-8/no-NUL/trailing-whitespace inspection passed. Deterministic fixtures only; no real-model, typing, hosted-CI, or production verification.

Latest source commit: 9a81227bbf3a6d8e84f4c3e553a7d62c163197bd
Latest source tree: 56cbfbee13729c736d130f9932fb23421742f55b
Latest segment: work/construction/segments/0151-task-score-lineage.md
Segment SHA-256: cfcbe2a64352172959a552d18fcb7f69517326edf96f4f05b56a0af3a3cf3d14
Evidence: work/construction/evidence/0151-task-score-lineage.json
Evidence SHA-256: a79c6545fe4ccfcd5e6e4217d9108bea84c007cc1abb90c974ab05c9a07c62e7
Sequence: 151

Next: inspect process-restart and model-replacement continuity for the exact evaluator/score lineage, ensuring it remains historical evidence and cannot become current truth or a capability claim.
