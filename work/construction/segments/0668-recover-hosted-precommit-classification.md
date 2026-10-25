# Sequence 668: Recover from hosted pre-commit provenance classification

The sequence 667 documentation candidate was published as PR #2767 from verified main `00b8cc00e5d1b30e892fe380ec95bb6978f17712`. Its exact-head Required Quality Gate run `40171182811` completed the hosted Administrator strict audit, audit immutability, documentation bootstrap, focused import and pytest bootstrap, all required call phases, acceptance generation, and artifact upload. The gate failed during exact hosted pre-commit reconstruction because four local test provenance snapshots and the latest provenance pointer were classified as unknown dirty paths under `glow/test_runs/`.

PR #2767 was closed without merge. Its original branch and worktree remain preserved. The provenance bytes are retained under indexed `work/construction/evidence/` in this successor checkout, and the successor candidate restores `glow/test_runs/` to the verified main tree. This follows the existing classifier; it does not change or bypass hosted governance.

The sequence 667 documentation edit remains the bounded task. Its docs build and focused regression passed on the verified base; the exact same documentation bytes are used here. The local finalizer remains blocked by protected-memory Administrator access, so the successor commit and handoff must retain `[untested]`. Exact-hosted Required Quality Gate and CI remain mandatory before any merge.

Evidence: `work/construction/evidence/0668-recover-hosted-precommit-classification.json`.
