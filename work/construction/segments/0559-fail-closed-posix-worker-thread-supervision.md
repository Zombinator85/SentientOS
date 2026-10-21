# Sequence 559 — fail closed when POSIX signal custody is unavailable

POSIX `run_supervised()` installs process-wide SIGINT and SIGTERM handlers to terminate the supervised process group when its controller receives a signal. Python permits handler installation only from the main thread. Calls from a worker thread now raise `RuntimeError("posix_supervision_requires_main_thread")` before stage output or child creation. The regression attempts to start a marker-writing child from a worker thread and verifies that no child starts. This retains the controller-cancellation contract rather than silently offering timeout-only behavior. Windows behavior is unchanged.

Local focused verification passed: 15 tests passed and one Windows-only native test skipped on Linux. Strict Mypy, Python compilation, `git diff --check`, and prior 558-segment custody verification passed. Candidate CI, strict Administrator Quality Gate, hosted privileged pre-commit finalizer, separate PR metadata guard, Windows Custody, Docker, lint, invariants, Release, Codex CI, and Gradient passed.

PR #2576 merged normally as `30c2c524d15e28b510d01b8a6f2728fa2a471a2d`, tree `a2491cc93436404e2bf5f5de03869b389fb46823`, with ordered parents `fe409477c32bc6165093954014e3da12c9e14e77` and `082d67afcaca06b4c4aa0201e3f99514021bea6c`. The merge tree equals the exact candidate tree. Post-merge CI, Required Quality Gate, Docker, Nightly Self Check, Invariant Tests, Docs Deploy, Windows Custody, and Codex CI passed; Forge Smoke was skipped by condition. The evidence JSON records all candidate and post-merge run and artifact identities, remote source blobs, and ordered merge lineage. Protected and stale workspaces were not touched.

Verified main: `30c2c524d15e28b510d01b8a6f2728fa2a471a2d`, tree `a2491cc93436404e2bf5f5de03869b389fb46823`
Latest construction segment: `work/construction/segments/0559-fail-closed-posix-worker-thread-supervision.md`
Sequence: 559 (verified source merge reconciliation)

Next: verify the supervisor distinguishes process-group disappearance from descendant termination when a child deliberately escapes with `setsid()`.
