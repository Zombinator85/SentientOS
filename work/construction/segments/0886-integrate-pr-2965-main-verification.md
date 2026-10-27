# Sequence 886: integrate PR 2965 main verification

PR #2965 merged as `b9bc7a68fd68d9d9ebce10efa719db793ce548b3` with verified tree `89b7697440702a1be4d2c3f6223458dc9d309d8c`. Its exact candidate was `d9c403d75a869f365e886b3306052352d150df46`; the candidate tree matches the merge tree. All eight exact-candidate PR workflows passed: CI (40551313004), Codex CI (40551312889), Docker Image (40551312838), Lint Benchmark (40551313001), Invariant Tests (40551313030), Gradient null regression (40551312906), Release (40551312913), and Required Quality Gate (40551312903). The gate completed exact-candidate acceptance, strict Administrator audits, pre-commit reconstruction, hosted privileged finalization, and the metadata guard.

Remote `main` readback matches the merge commit. All six required post-merge push workflows succeeded: CI (40555536407), Codex CI (40555536565), Docker Image (40555536438), Required Quality Gate (40555536408), Docs Deploy (40555536392), and Invariant Tests (40555536531). CI documentation build and warnings-as-errors linkcheck passed. Forge Smoke (40555536567) was skipped by its workflow condition.

GitHub tree readback verified exact blob identities for the sequence-885 v3 head, active checkpoint, evidence, segment, and eighteenth immutable v3 shard. Custody verified all 885 predecessor sequences before this append. The v3 head remains bounded at 1373 bytes; this append adds one immutable predecessor-linked shard and updates only the head and active checkpoint. The read-only source preflight returned `correct_remote_and_local_base` for `b9bc7a68fd68d9d9ebce10efa719db793ce548b3`.

Evidence record: `work/construction/evidence/0886-integrate-pr-2965-main-verification.json`
