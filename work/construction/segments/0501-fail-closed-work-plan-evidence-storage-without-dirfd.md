# Sequence 501 — fail closed without descriptor-relative evidence access

PR #2501 fixes a race in the path-based work-plan evidence fallback. Its component checks could pass, then an ancestor could be replaced before a later filesystem operation traversed the path. A new regression reproduced the missing rejection.

The fallback now refuses canonical evidence reads and writes when descriptor-relative directory operations are unavailable. It checks existing path components for symlinks and containment, then returns a specific unsupported-storage error before creating directories or accessing evidence. Platforms with descriptor-relative support retain the pinned-directory path.

Three fallback-specific regressions pass, including refusal before creating directories, refusal before reading existing evidence, and rejection of a symlinked ancestor. Seven affected work-plan, executor, journal, and orchestration suites passed (93 tests); targeted Mypy and compilation passed. All exact-candidate hosted checks passed, including strict Administrator audits, acceptance, privileged finalization, and the separate pre-publication metadata guard. The three Quality Gate artifacts were independently downloaded and matched their GitHub SHA-256 digests. The finalizer bound candidate `f462991ee6b8df3f1b9f85dffee020519a90d46f` and tree `b43e2fcbb66e17f98022ccabb10c8697ee8d541b`; validation used the solo profile and did not request an exhaustive matrix.

PR #2501 merged with history preserved as signed merge `de26ab3847a09edbc42def8133603052ab192599`, preserving base `a1e7241b1935a895ffc49e97acb06da9e5a9a1d7` and candidate `f462991ee6b8df3f1b9f85dffee020519a90d46f` as ordered parents. Remote main resolves to the merge and the merge tree matches the exact candidate. Post-merge Quality Gate, Source Validation, self-check, builds, CPU smoke, invariants, docs, Helm, and deployment passed; Forge Smoke was skipped by its workflow condition.

No task execution, inference, production campaign, or transition was performed. Execution authority and append-only construction history were preserved.

Latest source merge: `de26ab3847a09edbc42def8133603052ab192599`, tree `b43e2fcbb66e17f98022ccabb10c8697ee8d541b`
Latest segment: `work/construction/segments/0501-fail-closed-work-plan-evidence-storage-without-dirfd.md`
Predecessor segment SHA-256: `1de8ce7c67afb9bffce9b0dbc82395bad42a84c765a5e78ae5dc02875a8de4f7`
Sequence: 501
