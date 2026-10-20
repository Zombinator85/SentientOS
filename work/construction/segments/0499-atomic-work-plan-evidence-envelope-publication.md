# Sequence 499 — atomically publish work-plan evidence envelopes

PR #2498 closes the interruption window after an external work-plan binding sidecar has been published but before the canonical evidence envelope is fully written. The envelope is now written and synchronized in a private same-directory temporary, atomically linked into place without replacement, and followed by a directory sync. Exact retries remain idempotent and conflicting contents fail closed.

The regression injects an envelope fsync failure after the sidecar is durable, verifies the complete sidecar remains while the canonical envelope and temporary are absent, then retries and validates the persisted evidence digest. The affected local suites passed (24 tests), targeted Mypy and compilation passed, and all exact-candidate hosted checks passed. The Quality Gate's strict Administrator audits, acceptance, privileged finalizer, and separate pre-publication metadata guard passed. Downloaded gate artifacts were independently checked against GitHub's SHA-256 digests; validation used the solo profile without requesting an exhaustive matrix.

PR #2498 merged with history preserved as `d7219eb7673fe627412383b0e041506ed961ceab`. The signed merge preserves base `e70d952579bbe8d5a5257f52ad6ba8f024ee61d7` and candidate `6bef514f1d4f530d5b478fce7bb6f7d4b6367aaf` as ordered parents, with tree `58837c6b924d0c39fd03e33a36cc4689c85af0e8`, identical to the candidate tree. Post-merge checks passed; Forge Smoke was skipped by its workflow condition.

No production task, inference, campaign, or transition was executed. Authority boundaries and append-only construction history were preserved.

Latest source merge: `d7219eb7673fe627412383b0e041506ed961ceab`, tree `58837c6b924d0c39fd03e33a36cc4689c85af0e8`
Latest segment: `work/construction/segments/0499-atomic-work-plan-evidence-envelope-publication.md`
Predecessor segment SHA-256: `3fbd678500273d28cda7d2cee02a27e0880dc30eb57cbc2cd46ae3ac12bfa6d8`
Sequence: 499
