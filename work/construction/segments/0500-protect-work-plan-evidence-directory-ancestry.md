# Sequence 500 — guard work-plan evidence directory ancestry

PR #2499 closes the directory-ancestry gap in immutable work-plan evidence storage. On platforms with descriptor-relative APIs, the writer and reader traverse the canonical evidence directory without following symlinks, operate through the opened descriptor, and verify that the descriptor still names the canonical directory after access. The fallback validates each path component without accepting symlinks.

Regression tests reject symlinks at each ancestry level for both writes and reads, exercise the fallback rejection path, and swap an ancestor after secure open to prove the operation does not redirect evidence into the external target and fails its final directory identity check.

Seven affected work-plan, executor, journal, and orchestration suites passed (92 tests); targeted Mypy and compilation passed. All exact-candidate checks passed, including hosted Administrator audits, acceptance, privileged finalization, and the separate pre-publication metadata guard. The three hosted artifacts were independently downloaded and matched their GitHub SHA-256 digests. The finalizer bound candidate `69271640d8159832d761402cf187c32f52e5c004` and tree `ff75349ab29030665b259ef742b3603d92e8d099`; validation used the solo profile without requesting an exhaustive matrix.

PR #2499 merged with history preserved as signed merge `d2b987d23cdc86a371a15d096feda08024f9c3db`, preserving base `d7219eb7673fe627412383b0e041506ed961ceab` and candidate `69271640d8159832d761402cf187c32f52e5c004` as ordered parents. Remote main resolves to the merge and its tree matches the exact candidate tree. Post-merge Quality Gate, source validation, self-check, build, CPU smoke, invariants, Helm, and deployment passed; Forge Smoke was skipped by its workflow condition. The strict docs link check passed after the longer Sphinx external-link phase completed.

No production task, inference, campaign, or transition was executed. Authority boundaries and append-only construction history were preserved.

Latest source merge: `d2b987d23cdc86a371a15d096feda08024f9c3db`, tree `ff75349ab29030665b259ef742b3603d92e8d099`
Latest segment: `work/construction/segments/0500-protect-work-plan-evidence-directory-ancestry.md`
Predecessor segment SHA-256: `a51c1db481d2fcd8f1b0e5948ba1e00e24e0d6e990e2f6927ef6f5df6993691f`
Sequence: 500
