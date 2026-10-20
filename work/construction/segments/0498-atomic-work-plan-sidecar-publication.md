# Sequence 498 — atomically publish work-plan evidence sidecars

PR #2496 closes the interrupted-write gap in immutable work-plan evidence bindings. The writer now stages bytes in a private same-directory temporary file, flushes and synchronizes the file, publishes the completed sidecar with an atomic no-overwrite hard link, and synchronizes the containing directory. Exact existing bytes remain idempotent; conflicting bytes still fail closed.

The interruption regression injects an `fsync` failure before publication, verifies that neither the canonical sidecar nor its envelope exists and that the temporary file is removed, then retries and confirms successful canonical readback. This makes the retry path safe without treating temporary or partial data as canonical evidence.

The focused evidence-bound and executor suites passed, targeted Mypy and compilation passed, and all exact-candidate hosted workflows passed. The Required Quality Gate's strict Administrator audits, acceptance, privileged finalizer, and separate pre-publication metadata guard passed. Downloaded quality-gate artifacts were independently checked against GitHub's published SHA-256 digests and bind to candidate `a43018f58e796367ece41e4a85e98419e0f8bf37`, tree `cf77d77cb58fbef561427e52c991ce4b0a9c10a8`.

PR #2496 merged without squashing as `803f4d004dbc853424a507beba9980c706c9266c`. The signed merge commit preserves verified main `a20f300d3639539df977be67452f0eedde39b890` and the exact candidate as ordered parents. Remote `main` independently resolves to the merge commit and tree `cf77d77cb58fbef561427e52c991ce4b0a9c10a8`. Post-merge CI, Quality Gate, build, CPU smoke, invariants, docs, Helm, and deployment passed; Forge Smoke was skipped by its workflow condition.

No task execution, inference, production campaign, or transition was performed. No authority boundary or append-only evidence rule was changed.

Latest source merge: `803f4d004dbc853424a507beba9980c706c9266c`, tree `cf77d77cb58fbef561427e52c991ce4b0a9c10a8`
Latest segment: `work/construction/segments/0498-atomic-work-plan-sidecar-publication.md`
Predecessor segment SHA-256: `3089ccefcb21807d423255a7bce19f1e5300849d5010d921c742803887de8699`
Sequence: 498
