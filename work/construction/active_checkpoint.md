# Active construction checkpoint

Sequence 306 records PR #2286 integrated into `main` at `c897cc91f046592655506364f197a0b4d2e258ec`, tree `27ddb031801f1815658f90cea6e5fe4dd46543bd`. GitHub comparison confirms the merge commit is one commit ahead of the verified PR head, zero behind, with zero tree differences. The three-commit PR history is preserved.

The nightly audit workflows now use explicit, least-privilege paths. The read-only workflow keeps `contents: read`; the repair workflow retains only `contents: write` and `pull-requests: write`. Both require strict verification through noninteractive sudo; repair planning and application use the safe planner/apply tools, preserve run-scoped evidence, and leave unresolved findings as failures. Hosted PR CI and the protected finalizer passed; post-merge CI, quality gate, invariants, Docker, Codex CI, and Docs Deploy passed on the exact main commit.

The Federation Health updater still lacks a post-merge execution record. Its workflow configuration and manual-dispatch capability do not establish that a run occurred. No scheduled or dispatched run was present in the Actions feed at 05:20 UTC. The next hourly cron boundary is 06:00 UTC.

The sequence-286 deleted-payload limitation remains recorded: nine known payloads and one unidentified payload are unrecoverable. No historical payload was reconstructed or omitted.

Next dependency: obtain a successful post-merge Federation Health run; inspect the Administrator preflight and verify that any generated commit changes only `docs/FEDERATION_HEALTH.md`, then append the execution evidence.

Verified main commit: `c897cc91f046592655506364f197a0b4d2e258ec`
Verified main tree: `27ddb031801f1815658f90cea6e5fe4dd46543bd`
Latest segment: `work/construction/segments/0306-repair-nightly-audit-workflows.md`
Sequence: 306
Latest segment SHA-256: `9f07204e28e8e5b0f0a6e9004c60ea054a1adebe283330a852f52422d7b3dc79`
