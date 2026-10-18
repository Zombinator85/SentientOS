# Active construction checkpoint

Latest verified `main`: `9b0595f2384a70f8b2540240b157b90061368104`, tree `963912b175a6ea1f0191fcdc7d57fe24e63af345`. PR #2343 merged normally with both parents preserved. Candidate and post-merge CI, QG, Docker, invariants, Codex CI, Docs Deploy, and feedback succeeded; Forge Smoke was skipped by configured conditions. The post-merge QG artifact confirms 29/29, UID 0, exact source/tree, clean strict and immutability audits, and source unchanged.

Sequences 349–350 corrected and verified a test-fixture race without changing production serving behavior. Sequences 351–352 record the evidence integrations and main verification. Sequence 353 records historical scheduled Federation Health execution and a candidate offset to minute 17 after a multi-hour schedule gap.

PR #2344 is open as a draft. Its only source changes are the Federation Health cron minute and a workflow contract test; the health job remains read-only and Administrator-gated, with publisher write access isolated. Local affected tests pass. The first hosted QG passed audits and acceptance but failed its finalizer because its event's PR title differed from the commit subject; the PR title is corrected, and a fresh synchronization event is required before finalizer evidence can pass.

A historical scheduled run succeeded on source `f0564c9f780e1f86a53e84348ec4a4a9534c0e48`, but no current-source scheduled success is claimed. Changed-output fixture publication remains unrun; the GitHub connector cannot dispatch Actions. A supported workflow dispatcher or operator-started `publication_fixture=true` run is still required to prove changed-output PR creation. Preserve sequence-286 provenance-loss evidence and the stale sequence-178 workspace.

Latest construction segment: `work/construction/segments/0353-shift-federation-schedule-off-top-of-hour.md`
Latest segment SHA-256: `9a9e131dc215706b3f6cc39cabc2a01a9135448dd4f4833d786ce5bc5ee3c941`
Sequence: 353
