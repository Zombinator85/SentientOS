# Sequence 887: integrate PR 2966 main verification

PR #2966 merged as `0ca25be2c8f48996f26deb771b508b229ec12a96` with verified tree `28605b92bc75d1fd6fef0ef049591020c5ed6f6b`. Its exact candidate was `d998f39c2bc4f7e9879539d3e2d57f6c4fd80a1a`; the candidate tree matches the merge tree. All eight hosted PR workflows passed: CI (40557846440), Codex CI (40557846445), Docker Image (40557846272), Lint Benchmark (40557846540), Invariant Tests (40557846315), Gradient null regression (40557846356), Release (40557846320), and Required Quality Gate (40557846501). The gate completed exact-candidate acceptance, strict Administrator audits, pre-commit reconstruction, privileged landing finalization, and metadata guard.

Remote `main` readback matches the merge commit. All six required post-merge push workflows succeeded: CI (40558639766), Codex CI (40558639796), Docker Image (40558639804), Required Quality Gate (40558640148), Docs Deploy (40558640028), and Invariant Tests (40558639851). Forge Smoke (40558639963) was skipped by its workflow condition. The combined commit status readback returned no status entries.

GitHub tree readback verified the current v3 head, active checkpoint, sequence-886 evidence and segment, and nineteenth immutable v3 shard by exact blob identity. Custody verified all 886 predecessor sequences before this append. The v3 head remains 1373 bytes; this append adds one immutable predecessor-linked shard and updates only the bounded head and active checkpoint. Source preflight returned `correct_remote_and_local_base` for `0ca25be2c8f48996f26deb771b508b229ec12a96`.

Evidence record: `work/construction/evidence/0887-integrate-pr-2966-main-verification.json`
