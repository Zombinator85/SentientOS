# Recovery state - sequence 870

PR #2949 merged as `d45049f816790d2c9048e27be2875b6d2b899eab` with verified tree `4e1c5402f1f5076fe3dc376177baa3e09c8347fc`. All eight hosted workflows passed on candidate `b23e4f7c16a3dbd0cfbbf77cefb1bb223257cc4e`; GitHub readback verified the v3 head, active checkpoint, sequence 869 evidence, and second shard. The connected post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 869 prior sequences before this append and verifies 870 sequences after it.

Latest verified main: `d45049f816790d2c9048e27be2875b6d2b899eab`, tree `4e1c5402f1f5076fe3dc376177baa3e09c8347fc`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Latest construction segment: `work/construction/segments/0870-integrate-pr-2949-main-verification.md`
Latest segment SHA-256: `46a4f217609353398ac73f47cc0e60da80c4a80741660a140c42a3114978f7fd`
Sequence: 870
Evidence: `work/construction/evidence/0870-integrate-pr-2949-main-verification.json`
Evidence SHA-256: `00ee290b020f77fd246468ca83caf57176a612c02d2bc03f59806c0e1c33151b`

Recovery: continue from verified main using `work/construction/index-v3.json`. Preserve the immutable v2 anchor, every predecessor-linked v3 shard, and all prior segment, evidence, checkpoint, and provenance bindings. Append bounded shards and update only the constant-size head and active checkpoint.

--- Previous checkpoint snapshot (sequence 869) ---

PR #2948 post-merge verification is recorded in segment `work/construction/segments/0869-integrate-pr-2948-main-verification.md` and evidence `work/construction/evidence/0869-integrate-pr-2948-main-verification.json`.
