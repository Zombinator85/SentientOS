# Sequence 871: integrate PR 2950 main verification

PR #2950 merged as `1b763ae1e01cefdad019534c6b7feb57ac61aaa2` with verified tree `f79c9a4696d7bf9d11def0c23b84367224d5bec5`. The exact candidate was `d4fa728a8bd51b7da8d20e1a9086b8dedd3d91a1`. All eight hosted workflows passed on that head, including CI, Codex CI, Docker Image, Gradient null regression, Invariant Tests, Lint Benchmark, Required Quality Gate, and Release. The Quality Gate completed hosted privileged audits, exact-candidate pre-commit reconstruction, and landing finalization.

Remote `main` readback matched the merge commit. GitHub file readback verified the v3 head, active checkpoint, sequence 870 evidence, and third immutable v3 shard by exact blob identity. The connected post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 870 predecessor sequences before this append.

The append adds only a bounded shard and updates the constant-size head and checkpoint. The v3 root remains 1,371 bytes; historical v1/v2 data and prior v3 shards remain unchanged.

Evidence record: `work/construction/evidence/0871-integrate-pr-2950-main-verification.json`
