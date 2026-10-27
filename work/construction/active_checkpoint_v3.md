# Recovery state - sequence 871

PR #2950 merged as `1b763ae1e01cefdad019534c6b7feb57ac61aaa2` with verified tree `f79c9a4696d7bf9d11def0c23b84367224d5bec5`. All eight hosted workflows passed on candidate `d4fa728a8bd51b7da8d20e1a9086b8dedd3d91a1`; GitHub readback verified the v3 head, active checkpoint, sequence 870 evidence, and third shard. The connected post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 870 prior sequences before this append and verifies 871 sequences after it.

Latest verified main: `1b763ae1e01cefdad019534c6b7feb57ac61aaa2`, tree `f79c9a4696d7bf9d11def0c23b84367224d5bec5`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Latest construction segment: `work/construction/segments/0871-integrate-pr-2950-main-verification.md`
Latest segment SHA-256: `0c793f88858aa0b696ca62b1d2ff0e0dc21a17974515d7f5f9cbce7e7edcac1e`
Sequence: 871
Evidence: `work/construction/evidence/0871-integrate-pr-2950-main-verification.json`
Evidence SHA-256: `b41231d2faf3da132a40baf8c89a5028b50957c86edda44b1c151e7a8ddee2de`

Recovery: continue from verified main using `work/construction/index-v3.json`. Preserve the immutable v2 anchor, all predecessor-linked v3 shards, and prior segment, evidence, checkpoint, and provenance bindings. Append bounded shards and update only the constant-size head and active checkpoint.

--- Previous checkpoint snapshot (sequence 870) ---

PR #2949 post-merge verification is recorded in segment `work/construction/segments/0870-integrate-pr-2949-main-verification.md` and evidence `work/construction/evidence/0870-integrate-pr-2949-main-verification.json`.
