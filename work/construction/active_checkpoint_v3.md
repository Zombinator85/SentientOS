# Recovery state - sequence 875

PR #2954 merged as `bb6cb22e3f7968f17c10f154a0d1d604671dddd2` with verified tree `3a024d72ca4b24c17d6e1e66bba63db3b8d40bef`. All eight hosted workflows passed on candidate `d10cd283d9977837a3c101cc39c6c898aedd494d`; GitHub readback verified the v3 head, checkpoint, sequence 874 evidence, and seventh shard. The connected post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 874 prior sequences before this append and verifies 875 sequences after it.

Latest verified main: `bb6cb22e3f7968f17c10f154a0d1d604671dddd2`, tree `3a024d72ca4b24c17d6e1e66bba63db3b8d40bef`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Latest construction segment: `work/construction/segments/0875-integrate-pr-2954-main-verification.md`
Latest segment SHA-256: `fa186ac1bf0aa80d52bbc56bcee9ea49471cbafe641e7e11e6e8254297d50dcd`
Sequence: 875
Evidence: `work/construction/evidence/0875-integrate-pr-2954-main-verification.json`
Evidence SHA-256: `613af1336c02d3335f82914ec703bf2c44ed1a503f513d3eff5ebed5f8113bec`

Recovery: continue from verified main using `work/construction/index-v3.json`. Preserve the immutable v2 anchor, every predecessor-linked v3 shard, and prior segment, evidence, checkpoint, and provenance bindings. Append bounded shards and update only the constant-size head and active checkpoint.

--- Previous checkpoint snapshot (sequence 874) ---

PR #2953 post-merge verification is recorded in segment `work/construction/segments/0874-integrate-pr-2953-main-verification.md` and evidence `work/construction/evidence/0874-integrate-pr-2953-main-verification.json`.
