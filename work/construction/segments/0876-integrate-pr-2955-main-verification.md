# Sequence 876: integrate PR 2955 main verification

PR #2955 merged as `2edb2ccd0d9a55008f31d4ae3c2dd7f1f2aea5dd` with verified tree `933516d81c8a7ec977fb30fa1bd4f757d2a25e49`. The exact candidate was `9ddb02405194d2669fafff44e2a5cf9b9b74e4b4`. All eight hosted workflows passed on that head: CI, Codex CI, Docker Image, Gradient null regression, Invariant Tests, Lint Benchmark, Required Quality Gate, and Release. The Quality Gate completed hosted privileged audits, exact-candidate reconstruction, and landing finalization.

Remote `main` readback matched the merge commit. GitHub file readback verified the v3 head, checkpoint, sequence 875 evidence, and eighth immutable v3 shard by exact blob identity. The connected post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 875 predecessor sequences before this append.

The v3 head remains 1,371 bytes. This append adds one immutable predecessor-linked shard; the v2 anchor and all previous shards remain unchanged.

Evidence record: `work/construction/evidence/0876-integrate-pr-2955-main-verification.json`
