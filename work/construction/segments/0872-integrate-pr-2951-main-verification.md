# Sequence 872: integrate PR 2951 main verification

PR #2951 merged as `6579f13bb2d575191c964fdfa19d9430d3b58cad` with verified tree `b819b090edb46614bc31926fc71fb3627b2e8bea`. The exact candidate was `97d168a19eedaedd87434f7aa33093fad10442c7`. All eight hosted workflows passed on that head, including CI, Codex CI, Docker Image, Gradient null regression, Invariant Tests, Lint Benchmark, Required Quality Gate, and Release. The Quality Gate completed hosted privileged audits, exact-candidate reconstruction, and landing finalization.

Remote `main` readback matched the merge commit. GitHub file readback verified the v3 head, active checkpoint, sequence 871 evidence, and fourth immutable v3 shard by exact blob identity. The connected post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 871 predecessor sequences before this append.

The append adds only a bounded shard and updates the constant-size head and checkpoint. The v3 head remains 1,371 bytes; the immutable v2 history anchor and all earlier shards are unchanged.

Evidence record: `work/construction/evidence/0872-integrate-pr-2951-main-verification.json`
