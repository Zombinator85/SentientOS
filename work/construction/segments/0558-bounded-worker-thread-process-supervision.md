# Sequence 558 — avoid child leaks when supervision starts on a worker thread

`run_supervised()` previously started a subprocess before installing POSIX controller signal handlers. Python rejects `signal.signal()` from a worker thread, so the call could fail after launching a child and leave it unsupervised. The supervisor now installs process-wide handlers only from the main thread; worker-thread calls remain bounded by their configured timeout. A regression runs the timeout path in a worker thread and verifies that it returns without a signal-handler installation error. Controller-wide signal cancellation remains available to main-thread supervisors; the repository’s production call sites remain main-thread invocations.

Local focused verification passed: 15 tests passed and one Windows-only native test skipped on Linux. Strict Mypy, Python compilation, and `git diff --check` passed. Candidate CI, strict hosted Administrator audits, the 45-node Quality Gate, privileged pre-commit finalizer, separate PR metadata guard, Windows Custody, Docker, lint, invariants, Release, Codex CI, and Gradient passed. An initial Quality Gate run rejected a PR-title/commit-subject mismatch; the PR title was corrected to match the commit, and the rerun passed without source or gate changes.

PR #2574 merged normally as `a23e638c3a2653a79cb544ca08204b49839aacea`, tree `e063948428b16d16339679ccac75a78ca3c9d437`, with ordered parents `5cd9b0239058a28b0b7daf680f4bfe73b11918b5` and `8f81cfefa307e002521d19da4efd7b6a3491f9e9`. The source merge tree equals the exact candidate tree. Post-merge CI, Required Quality Gate, Docker, Nightly Self Check, Invariant Tests, Docs Deploy, Windows Custody, and Codex CI passed; Forge Smoke was skipped by condition. The paired JSON records exact runs, artifacts, source blobs, the metadata correction, and merge lineage. Protected and stale workspaces were not touched.

Verified main: `a23e638c3a2653a79cb544ca08204b49839aacea`, tree `e063948428b16d16339679ccac75a78ca3c9d437`
Latest construction segment: `work/construction/segments/0558-bounded-worker-thread-process-supervision.md`
Sequence: 558 (verified source merge reconciliation)

Next: examine whether the worker-thread timeout behavior should fail closed when controller-wide signal custody is required, without overclaiming cancellation coverage.
