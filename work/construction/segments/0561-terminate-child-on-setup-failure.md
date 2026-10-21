# Sequence 561 — terminate the child if supervision setup fails

run_supervised() launched a process before constructing its selector and installing signal handlers, but cleanup began only after that setup. If selector or handler setup failed, the controller could exit while the child remained alive. The supervisor now covers all post-Popen setup with cleanup that terminates the process group, reaps the root process, closes pipes and the selector, restores installed handlers, and re-raises the setup error.

A POSIX regression waits for proof that the child started, injects selector-construction failure, then checks that the child's delayed marker is not written. Existing process-group, escaped-descendant, worker-thread, timeout, and Windows coverage remains in place.

The focused process-supervision module passed: 17 passed, 1 Windows-only native test skipped on Linux. Avatar-authoring caller tests: 12 passed. Strict Mypy, Python compilation, and git diff --check passed.

The hosted Quality Gate's source-bound acceptance was extended from 45 to 46 exact nodes. Its manifest and provenance both bind candidate 676c7ceb6068d6eee3c69330263d3c39c967ead1; all 46 call-phase nodes passed, including the new setup-failure regression. Actual Administrator audits, hosted pre-commit finalization, candidate finalization, and the separate pre-publication metadata guard passed.

PR #2580 merged normally as 31711da42f3e128333138a2982e30d9e94e5d2b2, tree 11ee45ab1873a509f570604885dbe1a661dc8226, with ordered parents 71a700dfe32961c2c8b0a0719d59c7a2b37d0348 and 676c7ceb6068d6eee3c69330263d3c39c967ead1. The merge tree equals the exact candidate tree. Post-merge CI, Quality Gate, Docker, Docs Deploy, Nightly Self Check, Windows Custody, Invariants, and Codex CI passed; Forge Smoke was skipped by condition. The paired evidence JSON records exact run IDs, artifact digests, source blobs, and lineage.

No production transition, inference, or actuation was run. Protected and stale workspaces were not touched.

Verified main: 31711da42f3e128333138a2982e30d9e94e5d2b2, tree 11ee45ab1873a509f570604885dbe1a661dc8226
Latest construction segment: work/construction/segments/0561-terminate-child-on-setup-failure.md
Sequence: 561 (verified merge reconciliation)

Next: ensure controller exceptions terminate the process group even when the supervised root has already exited.
