# Recovery state - sequence 874

PR #2953 merged as `f499ce6882dc5a68a009a216ff8ebd9ac539f076` with verified tree `06dd494f07afd49a4ea9a5fc47c33f06c2203895`. All eight hosted workflows passed on candidate `560b00259cccb43c5cd53dbbe0d12f820a3eabcf`. CI required a standard GitHub rerun after the first PR-triggered run left a queued Helm check; the rerun passed all CI jobs. GitHub readback verified the v3 head, checkpoint, sequence 873 evidence, and sixth shard. Post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 873 prior sequences before this append and verifies 874 sequences after it.

Latest verified main: `f499ce6882dc5a68a009a216ff8ebd9ac539f076`, tree `06dd494f07afd49a4ea9a5fc47c33f06c2203895`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Latest construction segment: `work/construction/segments/0874-integrate-pr-2953-main-verification.md`
Latest segment SHA-256: `def7f6f00298c7ee5edc7a02e2003a213c46922f50d4ff65bef067b7b35488d5`
Sequence: 874
Evidence: `work/construction/evidence/0874-integrate-pr-2953-main-verification.json`
Evidence SHA-256: `2958237310c9d97932aff29be3a276c7b58d4726220ed6f96e62c85e40f3b167`

Recovery: continue from verified main using `work/construction/index-v3.json`. Preserve the immutable v2 anchor, all predecessor-linked v3 shards, and prior segment, evidence, checkpoint, and provenance bindings. Append bounded shards and update only the constant-size head and active checkpoint.

--- Previous checkpoint snapshot (sequence 873) ---

PR #2952 post-merge verification is recorded in segment `work/construction/segments/0873-integrate-pr-2952-main-verification.md` and evidence `work/construction/evidence/0873-integrate-pr-2952-main-verification.json`.
