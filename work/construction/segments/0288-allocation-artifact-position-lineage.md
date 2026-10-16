# Sequence 288 — Retain deferred position lineage in the durable allocation artifact

Sequence 287’s Required Quality Gate passed on the exact remote SHA `02de64ffe4b3fa91b4413a826a6d8be4849e0039` and tree `8b849b2f599a2be884429132345e4a2eb789f38e`; the verified hosted audit ran as effective UID 0. Its downloaded gate artifact matched GitHub’s reported digest and showed strict audit plus immutability success. The sequence-287 CI and Invariant Tests are still running.

Sequence 287 carried scoped position identities into selected and deferred allocator results and plan evidence. This follow-up closes the remaining artifact gap: the durable goal-allocation JSON now includes the exact position identity and posture for each deferred goal, including the exact omitted-state identity for projection-bound omissions. Canonical persisted plan evidence and the allocation artifact are checked against the same identities in the daemon reconstruction test.

The only behavior change is additional attributable evidence. Goal ordering, selected and deferred decisions, budgets, authority, plan task content, and execution remain unchanged. This evidence does not represent task execution or success.

The exact committed source is `5300ddc79d5aa79849fa004530f5d23a368f3f20` with tree `ac9cfe9c09ab748aba0359dcfab6c6ce8f6b4afe`. Its canonical plan-only integration suite passed 5/5 with no skips or failures. Compilation and diff checking passed. The repo-wide Mypy baseline ratchet reported `mypy_baseline_improved`, zero new errors, 1,053 matched existing errors, and 37 retired records. A supplemental targeted Mypy command reported one existing `no-any-return` at `sentientos/orchestrator.py:1225`; the parent source produces the same error at the corresponding line, confirming it is not introduced by this increment.

The repository-wide provenance analyzer continues to report the known historical chain gap from sequence 286’s accidental cleanup (nine payloads unavailable and one unidentified record). New run records are preserved; this increment does not claim recovery of the earlier missing payloads.
