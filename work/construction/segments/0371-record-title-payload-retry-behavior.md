# 0371 — Record title-payload behavior across privileged finalizer retries

## Hosted observation

Required Quality Gate run #39122735813 passed hosted Administrator strict audit and all 29 acceptance nodes. Its finalizer again stopped at the workflow's exact PR-title/commit-subject guard. The synchronize event had captured PR title `[codex:construction-evidence] reconcile scheduled workflow evidence`; the latest commit subject was `[codex:construction-evidence] record privileged landing title contract`. The logs expose those values and the equality test before the privileged finalizer call.

Renaming the draft PR after GitHub enqueues a run does not change that run's event payload. Rerunning the same failed job also preserves the captured title. The guard worked correctly and the finalizer did not run.

## Corrective sequence

The draft PR title has now been set, before the next head update, to `[codex:construction-evidence] record title-payload retry behavior`. The next descendant commit will use that identical subject. Its new synchronize event should then bind matching values. The complete hosted gate, including the privileged finalizer, remains required before landing. No guard, test, privilege, runtime, or cognition behavior is changed.

## Custody

Evidence JSON: `work/construction/evidence/0371-record-title-payload-retry-behavior.json`

Evidence SHA-256: `633526bc6fe4e14af15b34b2ea5b2365f2cafb7ba17de3d3bba4bd3c58f9e9be`

Evidence bytes: `2224`

Source candidate: `4606778f352d38ca86b0f233719c495792c17b7d` (tree `c0c3d5926b9ae81a51066830086da7dd525164d5`).

Predecessor: `segment-sha256:395ef63cd9f4a6ff07d2e1add0eef9387ba5658e8ab309963cc9cd18f2cb3a40`
