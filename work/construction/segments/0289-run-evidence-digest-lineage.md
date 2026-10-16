# Sequence 289 — Bind execution run artifacts to the verified plan evidence

Sequence 288’s Required Quality Gate passed on remote SHA `4629a27e1e670e62b69bc12c3a0ae314adaefa7f` and tree `76edab3a50dc8af3c1d89c47d72797093cbca17f`. Its hosted gate ran as effective UID 0. The downloaded artifact matched GitHub’s reported digest and recorded strict audit, immutability, and unchanged-source success. Sequence 288’s Invariant Tests passed; its full CI is still running.

The prior increment retained history identities through allocation artifacts and canonical plan evidence, but execution run records bound only the plan digest. A later consumer could not prove which exact, validated evidence digest had been required when that run was produced.

Canonical execution now emits work-run schema v3 with the exact expected evidence digest. The executor validates the immutable plan evidence before tasks, stores its digest in the run, and requires it to match on replay. Run loading revalidates the plan evidence and the digest. Legacy/manual schema-v2 runs remain supported when no evidence digest is expected. The existing task statuses remain reports of execution attempts; planning evidence does not become proof of task success or completion.

The exact committed source is `e7d874feb9c5aec7015d4c34f127a335336a9bcf` with tree `eb1c60d608b1450cce6a2e7c86453b8dcce85678`. After commit, the affected executor, run loader, and completion checks passed 36/36 with no skips or failures. Targeted Mypy passed; the repo-wide baseline ratchet reports zero new errors. Compilation, diff checking, and construction custody passed.

An earlier collection attempt used a nonexistent test path and exited before executing tests; it is retained as exploratory provenance and is not counted as verification. The next exact-SHA run passed. The old repository-wide provenance chain gap remains disclosed: sequence 286 cleanup removed nine payloads and one unidentified record, and these bytes cannot be recovered from existing workspace evidence.
