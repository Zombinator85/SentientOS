## 2026-10-12 — prove remote advancement without local fetch is not accepted

- Candidate parent: `ada178bc412a9a2ebf82d225575947c7d959a568`; tree `9990918a63841f7b78b5b5b329dfc07a899f7eee`.
- Source-bound `scripts/construction_source_preflight.py` distinguishes remote commit identity from the local checkout and returns `remote_commit_object_unavailable` when `ls-remote` observes a new head not present in the local object database. It also checks an expected-head lease before attempting local ancestry.
- Added a disposable local bare-remote case that advances the branch from a second clone without fetching into the inspected checkout. It proves the stale local source is not accepted, and expected-head checking reports `branch_advanced_during_publication`.
- All nine preflight cases passed, including dirty/stale base, divergence, same-tree/new-commit, remote mismatch, unreachable remote, and publication race. Compilation and diff checks passed. Full result: `work/construction_source_preflight_acceptance.json`.
- No production preflight code change was needed. The helper intentionally does not fetch; a remote commit absent locally remains unavailable until exact source acquisition is performed.
- Next: reconcile the stale historical workspace against exact remote owner blobs with bounded source reads; only uniquely valuable differences should be preserved as candidates. Then continue tracing minimum hosted runtime completion and unresolved deployment blockers.
