# Recovery state - sequence 876

PR #2955 merged as `2edb2ccd0d9a55008f31d4ae3c2dd7f1f2aea5dd` with verified tree `933516d81c8a7ec977fb30fa1bd4f757d2a25e49`. All eight hosted workflows passed on candidate `9ddb02405194d2669fafff44e2a5cf9b9b74e4b4`; GitHub readback verified the v3 head, checkpoint, sequence 875 evidence, and eighth shard. Post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 875 prior sequences before this append and verifies 876 sequences after it.

Latest verified main: `2edb2ccd0d9a55008f31d4ae3c2dd7f1f2aea5dd`, tree `933516d81c8a7ec977fb30fa1bd4f757d2a25e49`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Latest construction segment: `work/construction/segments/0876-integrate-pr-2955-main-verification.md`
Latest segment SHA-256: `a3f31bf0ec5216e4f3a7aec8c5695ec00cd0218235a61a327c550fbef7d79bf3`
Sequence: 876
Evidence: `work/construction/evidence/0876-integrate-pr-2955-main-verification.json`
Evidence SHA-256: `e25b4adef88360f313fc5739f9c9dd01fadaf0b6756d9599e0a29b633072ca69`

Recovery: continue from verified main using `work/construction/index-v3.json`. Preserve the immutable v2 anchor, every predecessor-linked v3 shard, and prior segment, evidence, checkpoint, and provenance bindings. Append bounded shards and update only the constant-size head and active checkpoint.

--- Previous checkpoint snapshot (sequence 875) ---

PR #2954 post-merge verification is recorded in segment `work/construction/segments/0875-integrate-pr-2954-main-verification.md` and evidence `work/construction/evidence/0875-integrate-pr-2954-main-verification.json`.
