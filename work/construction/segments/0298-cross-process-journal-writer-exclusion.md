# Sequence 298 — Exclude competing journal writers across processes

Sequence 298 verifies that the journal's POSIX kernel lock and stale-snapshot check serialize independent writers in separate processes. Two workers recover the same empty journal before a barrier releases them to append different task starts. Exactly one append succeeds; the other receives `work_plan_journal_stale_writer`. Recovery finds one interrupted task and a single intact record, so the hash chain cannot fork.

The committed source candidate passed the seven affected journal, executor, CLI, progression, orchestrator, load, and evidence-bound suites (57/57), changed-test Mypy, compilation, diff checks, and continuation custody (297 predecessor segments). The local source commit `06a406ba369710eb5d97d84dfe178608f5a55966` and GitHub source commit `1e284215ae8d80262a67e9377c2c5199d5ceac3b` share tree `9ff2911f599cdcae1988b03f4b628558c449b532`; the changed test blob and remote branch tree were independently read back.

GitHub CI `38985300860`, Invariant Tests `38985300827`, and Required Quality Gate `38985314172` passed on the exact remote source SHA. The independently downloaded gate artifact `12083000749` matched GitHub's SHA-256 `9e2422ff2e1fb28aac2dd126cbbc29a983783b852e0b061a288238b99097eccd`. It records effective UID 0 and Administrator verification, exact SHA/tree binding, unchanged source and repository identity, strict audit success, and immutability success.

The sequence-286 provenance limitation remains: nine known deleted payloads and one unidentified deleted payload are unrecoverable. No historical payload was reconstructed or silently omitted.

Next dependency: exercise a process crash inside the real append path after a partial write, proving the kernel releases the lock and recovery preserves and rejects the incomplete bytes without repair.
