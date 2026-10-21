# Sequence 518 — report stale Federation Health snapshots

A successful scheduled Federation Health artifact revealed that its configured log snapshot's latest event was `2025-06-05T16:25:13.805813Z`, while the run was on `2026-10-21`; the generated report showed zero recent events but labeled the result `quiet`. The report already disclosed that it reads a configured local snapshot rather than live telemetry. The generator now labels a snapshot `stale` when it contains valid events but its newest event predates the requested reporting window. A recent event remains `healthy`, an empty or unusable snapshot remains `quiet`, a missing file remains `no log`, and future timestamps are still excluded from the recent count.

The new regression is included as a source-bound hosted acceptance node. The existing Federation Health workflow triggers on pushes changing `federation_health_badge.py`; after this candidate is merged, that path will produce a current-main hosted execution artifact without changing its Administrator preflight, audit evidence binding, or scoped publisher permissions.

Local verification passed 98 affected tests with 0 failures and 0 skips. Compileall, AST parsing, workflow YAML parsing, diff checks, and custody over 517 predecessor segments passed. The canonical Mypy baseline reported `mypy_baseline_improved`, zero new errors, and 40 retired existing errors. Exact source tree and modified source blobs matched independent GitHub readback. Exact-candidate hosted verification is pending. No production transition, activation, serving, inference, or writeback was performed.

Verified main: `45d49ec2e2cab9a9158686f9bf7536801b642883`, tree `6b35806f17cce6a2814e6693f8a8156100d53a20`
Implementation candidate: `9357dede0d6fc6c5a829f084cf5905f77f2fc4aa`, tree `a25269c3e6ec480343b8cd7fa3607617ead0f41e`
Sequence: 518 (candidate pending hosted verification)
