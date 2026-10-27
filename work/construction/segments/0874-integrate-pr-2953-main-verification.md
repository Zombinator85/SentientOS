# Sequence 874: integrate PR 2953 main verification

PR #2953 merged as `f499ce6882dc5a68a009a216ff8ebd9ac539f076` with verified tree `06dd494f07afd49a4ea9a5fc47c33f06c2203895`. The exact candidate was `560b00259cccb43c5cd53dbbe0d12f820a3eabcf`. All eight hosted workflows passed on that head: CI, Codex CI, Docker Image, Gradient null regression, Invariant Tests, Lint Benchmark, Required Quality Gate, and Release. CI was rerun through GitHub's normal workflow action after its first PR-triggered run left a queued Helm check; the rerun completed successfully with every CI job passing. The Quality Gate completed hosted privileged audits, exact-candidate reconstruction, and landing finalization.

Remote `main` readback matched the merge commit. GitHub file readback verified the v3 head, checkpoint, sequence 873 evidence, and sixth immutable v3 shard by exact blob identity. The connected post-merge workflow lookup returned no runs and combined statuses were empty; none are claimed. Custody verified all 873 predecessor sequences before this append.

The v3 head remains constant at 1,371 bytes. This append adds one immutable predecessor-linked shard and preserves the v2 anchor and all prior history.

Evidence record: `work/construction/evidence/0874-integrate-pr-2953-main-verification.json`
