# Sequence 560 — report escaped descendants as unconfirmed

`run_supervised()` previously treated disappearance of its POSIX process group as proof that every descendant had terminated. A child can call `setsid()`, leave that group, and continue running. The result now keeps `descendants_confirmed_terminated` false and reports only that the original process group is absent. A regression starts a detached child, times out its parent, and proves the child survives long enough to write a marker; existing process-group timeout coverage also asserts the conservative evidence.

Local focused verification passed: 16 tests passed and one Windows-only native test skipped on Linux. Strict Mypy, Python compilation, and `git diff --check` passed. Candidate CI, strict Administrator Quality Gate, hosted privileged finalizer, separate metadata guard, Windows Custody, Docker, docs, lint, invariants, Release, Codex CI, and Gradient passed.

PR #2578 merged normally as `1042e955963d2dac5ef60c2930d0e089568c0024`, tree `0612883b39292d1e50a3d48cde7ed0d6443458c9`, with ordered parents `21710b8a4f34c2728105d1e3f3a9437588d620a8` and `e4c8ab6f14656305aec5c41dd8833c600fec8133`. The merge tree equals the exact candidate tree. Post-merge CI, Quality Gate, Docker, Docs Deploy, Nightly Self Check, Windows Custody, Invariants, Codex CI, and CPU smoke all passed; Forge Smoke was skipped by condition. See the evidence JSON for exact run IDs, artifacts, source identities, and lineage.

An intervening scheduled Federation Health execution on the verified predecessor main completed both health generation and automatic report publication. Its report correctly said `stale` because it reads a configured local snapshot rather than live federation telemetry. The publisher updated PR #2511; GitHub requires approval before that bot-created PR's checks can run. This operational observation is recorded separately from sequence 560's exact source merge verification.

Verified main: `1042e955963d2dac5ef60c2930d0e089568c0024`, tree `0612883b39292d1e50a3d48cde7ed0d6443458c9`
Latest construction segment: `work/construction/segments/0560-report-escaped-descendants-as-unconfirmed.md`
Sequence: 560 (verified merge reconciliation)

Next: terminate and reap the supervised process if selector or signal-handler setup fails after `Popen` has already launched it.
