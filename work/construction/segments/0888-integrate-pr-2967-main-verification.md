# Sequence 888: integrate PR 2967 main verification

PR #2967 merged as `ea322c01227180f0f22ed93b00298f74a365eba2` with verified tree `3cc74f13d620587550dbd898fafd085742b17ec5`. Its exact candidate was `b56a6528961f014428f3f876d00c6184d7bbe62b`; the candidate tree matches the merge tree. All eight exact-candidate hosted workflows passed: CI (40563486787), Codex CI (40563486812), Docker Image (40563486838), Lint Benchmark (40563486848), Invariant Tests (40563486825), Gradient null regression (40563487019), Release (40563486819), and Required Quality Gate (40563486942). The gate completed exact-candidate acceptance, strict Administrator audits, pre-commit reconstruction, privileged landing finalization, and metadata guard.

Remote `main` readback matches `ea322c01227180f0f22ed93b00298f74a365eba2`. All six required post-merge push workflows succeeded: CI (40564244127), Codex CI (40564244101), Docker Image (40564244052), Required Quality Gate (40564244017), Docs Deploy (40564244435), and Invariant Tests (40564244018). Forge Smoke (40564244240) was skipped by its condition.

GitHub tree readback verified the exact candidate tree and its five changed blobs. Custody verified all 887 predecessor sequences before this append. Source preflight returned `correct_remote_and_local_base` for `ea322c01227180f0f22ed93b00298f74a365eba2`.

Evidence record: `work/construction/evidence/0888-integrate-pr-2967-main-verification.json`
