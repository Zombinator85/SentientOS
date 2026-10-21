# Sequence 554 — Support native Windows subprocess pipe draining

The bounded subprocess supervisor used `selectors.DefaultSelector` for POSIX pipes, but Windows selectors do not support anonymous subprocess pipes. On native Windows a supervised stage could therefore fail before it could drain stdout or stderr. The implementation now polls both Windows pipe handles with `PeekNamedPipe`, reads only the reported available bytes, recognizes broken-pipe EOF, and preserves bounded line buffering, heartbeat, timeout, and drain-deadline behavior. POSIX selector handling is unchanged. Windows descendant enumeration remains explicitly unconfirmed.

A regression writes concurrently to stdout and stderr beyond typical pipe capacity and proves both streams drain without deadlock. The test is included in Windows Custody hosted verification. Exact hosted acceptance now binds 42 nodes, and the workflow contract tests bind the Windows regression job and source selection. The focused supervisor module (11 tests) and hosted workflow contract module (51 tests) passed locally; compilation, strict Mypy, and diff checks passed.

PR #2567 merged normally as `3e435dd8db0a4ada125cdf7433a8744f3ddb9eee`, tree `68e40fe10352fb958ae778d4fe3f08e0adaf1f46`, with ordered parents `070f2b793e772a9a39378d77fad90493af8f8277` and `5759e87c686d4e5cecafcc6d4012fdd950a2632f`. The candidate Windows Custody check passed on `windows-latest`; exact-candidate CI, the 42-node privileged Quality Gate and pre-publication metadata guard, Docker, lint, invariants, Release, Codex CI, and Gradient checks passed. Candidate and post-merge CI include integrated resource-to-cognition, canonical planning/execution separation, Federation Health freshness, and transition receipt acceptance.

All post-merge checks on exact main passed: CI, Required Quality Gate, Docker, Docs Deploy, Nightly Self Check, Invariants, Windows Custody, and Codex CI. Forge Smoke was skipped by its configured condition. Exact run IDs, artifact identities, merge lineage, and source recovery details are in the paired evidence JSON.

Verified main: `3e435dd8db0a4ada125cdf7433a8744f3ddb9eee`, tree `68e40fe10352fb958ae778d4fe3f08e0adaf1f46`
Latest construction segment: `work/construction/segments/0554-windows-subprocess-pipe-draining.md`
Sequence: 554 (verified merge reconciliation)

Next: inspect the bounded subprocess supervisor's cancellation and descendant-lifetime semantics on Windows, and keep claims aligned with what the platform can prove.
