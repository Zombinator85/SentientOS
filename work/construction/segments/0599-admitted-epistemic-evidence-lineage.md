# Sequence 599 — active epistemic evidence follows admitted lineage

PR #2655 fixes the resident epistemic runtime's use of the append-only binding registry as though it were the active evidence set. Both snapshot ingestion and verified task-family outcome ingestion now reconstruct effective membership from admitted update-event additions and removals, while preserving uncommitted evidence appends for crash recovery. Explicitly removed bindings remain in immutable history and are not reactivated by later ticks.

Freshness variants of the same exact source fact are grouped by source and epistemic semantics. The most conservative posture is retained in effective state: an aged observation supersedes its prior current binding with the stale binding, and the state event records the removal as `source_reliability_revision`. No source records are rewritten or deleted.

The new lifecycle regression admits a current observation, advances the source builder clock beyond its freshness window, confirms that only the stale version is active and that the proposition becomes suspended, then admits withdrawal and repeats the same snapshot to prove the old binding is not revived. Both immutable freshness records remain present.

Exact candidate: `f330ecee7f8190781c32e6ce9a79d9d261631968`, tree `cbd693a248ea5163d27304b775fc961844044859`, parent verified main `5f9049e5da4aba273c1d1206d623684d5b10ded7`. Local focused epistemic development tests passed (29 tests); targeted mypy and Python syntax compilation passed. The nearest local checkout was sequence 565 and its repository-wide mypy invocation reported 357 existing diagnostics across 74 files, so it is not represented as current-main evidence.

All eight exact-candidate PR workflows passed: CI 39883318779, Required Quality Gate 39883318604, Release 39883318634, Codex CI 39883319003, Gradient null regression 39883318674, Invariant Tests 39883318605, Docker Image 39883318705, and Lint Benchmark 39883318624. The hosted gate passed strict audits with actual Administrator authority, exact acceptance binding, audit immutability, hosted finalizer, and the separate pre-publication metadata guard. CI passed the full test, source-validation, documentation, and Helm integration jobs.

PR #2655 merged normally as `6d9d409774eb8b8af7d750d49d7e8e7834c5741b`; the merged tree exactly matches the candidate tree, with verified main `5f9049e5da4aba273c1d1206d623684d5b10ded7` as first parent. No model inference, production transition, or goal execution occurred.

Sequence: 599 (verified source integration)
