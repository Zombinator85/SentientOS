# Recovery state - sequence 869

PR #2948 merged as `0d008510f69bc44a95a672486e32e4dd9f9a1369` with verified tree `247b57a5b9daa68ab62a24f9b576bca17ef0a19f`. All eight hosted workflows passed on candidate `fab47a77f81e2533bf570fbfb803923a163cb712`; GitHub readback verified the v3 head, checkpoint, and first shard. The connected post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 868 prior sequences before this append and verifies 869 sequences after it.

Latest verified main: `0d008510f69bc44a95a672486e32e4dd9f9a1369`, tree `247b57a5b9daa68ab62a24f9b576bca17ef0a19f`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Latest construction segment: `work/construction/segments/0869-integrate-pr-2948-main-verification.md`
Latest segment SHA-256: `72a8dc34b8f7e1b4222c9f49840219bc8830756abdd0552fe47530a14416ac36`
Sequence: 869
Evidence: `work/construction/evidence/0869-integrate-pr-2948-main-verification.json`
Evidence SHA-256: `80aa62b000cccdf7608c9aa5266df844295e8b922c6cab0a985deb637c069328`

Recovery: continue from verified main using `work/construction/index-v3.json`. Preserve the immutable v2 history anchor, every predecessor-linked v3 shard, and all prior segment, evidence, checkpoint, and provenance bindings. Append bounded shards and update only the constant-size head and active checkpoint.

--- Previous checkpoint snapshot (sequence 868) ---

PR #2947 post-merge verification is recorded in segment `work/construction/segments/0868-integrate-pr-2947-main-verification.md` and evidence `work/construction/evidence/0868-integrate-pr-2947-main-verification.json`.
