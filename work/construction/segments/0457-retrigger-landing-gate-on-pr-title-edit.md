# Sequence 457 — Retrigger the landing gate after PR title edits

A required-quality-gate run for PR #2424 used the title captured by its earlier pull-request event. The branch had advanced to a commit with a new matching PR title after that run started. Its logged `PR_TITLE` remained `[codex:test] preserve strict pre-commit finalizer assertion`, while the branch's then-current commit subject was `[codex:workflow] print exact pre-commit finalizer evidence`. The gate therefore stopped at its exact title check before reconstructing the parent workspace or invoking the pre-commit finalizer. Re-running that job reused the same event payload and failed at the same check.

This sequence makes title edits an explicit Required Quality Gate trigger and adds a regression assertion for that trigger. This lets the gate re-evaluate the exact PR candidate after metadata is corrected. The finalizer and metadata guard remain bound to the exact candidate and still require the PR title to match the commit subject; no pass condition or authority boundary is relaxed.

The current integrated source is main `0082e3d9d76337c2f25efb9defb49e40e87dc482`, tree `4e8cd83f5c0c1e533d7c215157ee4dfe79cbbed5`. The Required Quality Gate runs #39241673948 (job #118023728238) and its retry (job #118024580689) both stopped before pre-commit finalization due to the stale event title. Acceptance, hosted Administrator audit, strict checks, and exact-candidate checks preceding that title gate passed. Source change and exact-head acceptance remain subject to the current PR matrix.

No scheduled Federation Health execution on current main has yet been verified from this work. The report remains a configured local snapshot, not live telemetry. Historical provenance gaps and protected workspaces remain untouched.
