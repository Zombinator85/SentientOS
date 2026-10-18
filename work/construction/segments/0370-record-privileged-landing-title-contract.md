# 0370 — Record and correct the privileged landing title contract

## Hosted failure diagnosis

The first sequence-369 candidate quality-gate run, #39122354578, passed the hosted Administrator strict audit and all 29 exact acceptance nodes. Its finalizer step failed before invoking the finalizer: the workflow requires the pull-request title to match the latest commit subject byte-for-byte. The commit subject began with lowercase “reconcile” while the draft PR title used uppercase “Reconcile.”

The draft was renamed and recreated on the same head, then the failed job was rerun. GitHub retained the original workflow event title in `PR_TITLE`, so the equality guard failed again. This confirms a fresh candidate head and PR event are needed; editing PR metadata or replaying the old event is insufficient.

## Resolution

Keep the workflow title-equality assertion and the privileged finalizer intact. Preserve sequence 369 and its commit. This continuation records the failure and applies the existing contract to a new descendant: its commit subject and draft PR title must be identical. The new head must pass the complete quality gate, including finalizer, before landing.

No runtime source, cognition, or authority changed. The strict hosted audit and 29 acceptance tests passed in the failed run; only the finalizer handoff was blocked by title mismatch.

## Custody

Evidence JSON: `work/construction/evidence/0370-record-privileged-landing-title-contract.json`

Evidence SHA-256: `26e944a7d412f29ada057a6902784e5c63253115b270cf2316e3cc04c71017c0`

Evidence bytes: `2880`

Source candidate: `b4dc89c13ab773eafa048926a5f7ed3daeb82923` (tree `a03424d810a8843982d1a5a61720bd1e1ced6542`). Source identities for the quality-gate workflow and finalizer are in the evidence JSON.

Predecessor: `segment-sha256:36440e2bd9ccdbaf9c35b59d460e7f3f211f7f3816df554bcd98b7e844f18d5e`
