# Active construction checkpoint

Sequence 289 binds persisted canonical execution runs to the exact validated plan evidence digest. Work-run schema v3 stores and revalidates that digest; replay rejects mismatch. Legacy schema-v2 runs remain supported without evidence binding. The affected executor, work-run loader, and completion-check suite passed 36/36 with no skips or failures on exact source `e7d874feb9c5aec7015d4c34f127a335336a9bcf`, tree `eb1c60d608b1450cce6a2e7c86453b8dcce85678`. Targeted Mypy and the repo-wide baseline ratchet passed with zero new errors; compilation, diff, and custody checks passed.

Sequence 288’s Required Quality Gate passed on remote SHA `4629a27e1e670e62b69bc12c3a0ae314adaefa7f` and tree `76edab3a50dc8af3c1d89c47d72797093cbca17f`, with effective UID 0, strict audit and immutability success. Its Invariant Tests passed; its full CI remains in progress. Sequence 289’s hosted verification has not run yet.

Historical append-only provenance remains incomplete after sequence 286 cleanup: nine payloads and one unidentified record were lost. Sequence 289 preserves new run evidence, including one earlier missing-path collection failure, without treating it as test success.

Latest verified main: `d9fbac78dad9187065fcdeaf112bf641cf3508ea`
Latest verified main tree: `71d300a7ddd35343b710e3e52b58e4b02962825a`
Latest segment: `work/construction/segments/0289-run-evidence-digest-lineage.md`
Latest segment SHA-256: `4e3db2e2fcd56728f9572bde5e3c441a9a2f51ccc651da01da52db05929893c6`
Evidence: `work/construction/evidence/0289-run-evidence-digest-lineage.json`
Evidence SHA-256: `cc4c8d09181dea5fb54a60198c5d2f91c39223f1f6b8687c31617f2dfff3457e`
Sequence: 289

Next: carry the run evidence digest into completion review and prove that task-run status alone cannot satisfy a goal completion check.
