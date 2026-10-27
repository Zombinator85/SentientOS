# Recovery state - sequence 873

PR #2952 merged as `fd4282607432a9d5e625840491a94ea28a9fcb69` with verified tree `dacae62cb2ed99c50bbfc43ea88c65df4e7412dc`. All eight hosted workflows passed on candidate `61560175658e14e305f88849c5b66cf5558be107`; GitHub readback verified the v3 head, active checkpoint, sequence 872 evidence, and fifth shard. The connected post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 872 prior sequences before this append and verifies 873 sequences after it.

Latest verified main: `fd4282607432a9d5e625840491a94ea28a9fcb69`, tree `dacae62cb2ed99c50bbfc43ea88c65df4e7412dc`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Latest construction segment: `work/construction/segments/0873-integrate-pr-2952-main-verification.md`
Latest segment SHA-256: `76ba8fad6df7fb1225724291da03acb13dca5fd9591a640d72f79ebbae58a8e5`
Sequence: 873
Evidence: `work/construction/evidence/0873-integrate-pr-2952-main-verification.json`
Evidence SHA-256: `bfcdba5f56765af40cf1f8277531d26ea451968f1051ee237cca396c8bbebabc`

Recovery: continue from verified main using `work/construction/index-v3.json`. Preserve the immutable v2 anchor, every predecessor-linked v3 shard, and prior segment, evidence, checkpoint, and provenance bindings. Append bounded shards and update only the constant-size head and active checkpoint.

--- Previous checkpoint snapshot (sequence 872) ---

PR #2951 post-merge verification is recorded in segment `work/construction/segments/0872-integrate-pr-2951-main-verification.md` and evidence `work/construction/evidence/0872-integrate-pr-2951-main-verification.json`.
