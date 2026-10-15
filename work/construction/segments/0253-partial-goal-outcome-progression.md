# Sequence 253 - Partial forge outcomes do not satisfy dependent tasks

Forge apply reports with `partial_success` now produce a distinct `partial` task result and retain the report artifact plus an explicit reason. Work run and append-only journal validation preserve that status through recovery. The overall run remains partial, and verified goal state records retain the partial posture.

A dependent task still requires exact `success`; it remains skipped after a partial result. Independent tasks continue. This prevents an incomplete forge application from being treated as complete merely because the forge reported some progress.

Validation: goal executor run, plan, and work plan recovery suites passed (36 tests). Changed Python sources and tests compiled; `git diff --check` passed.

Limits: this increment records partial outcomes and gates dependencies, but does not automatically continue a forge application or claim goal completion. Further task-chain planning from verified later outcomes remains open.
