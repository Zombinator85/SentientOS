# Sequence 890: integrate PR 2969 main verification

PR #2969 merged as `a381b65d275d458b871930f0c76091e2b633c7a2` with verified tree `b1531b044e8f8c8fb21e6eb073369f5712870737`. The exact candidate was `38b0be679010635c9d205e7405d8ba0e5cb5ef21`; its tree matches the merge tree. All eight exact-candidate hosted workflows passed: CI (40567696301), Codex CI (40567696418), Docker Image (40567696407), Lint Benchmark (40567696281), Invariant Tests (40567696288), Gradient null regression (40567696346), Release (40567696594), and Required Quality Gate (40567696336).

The merged correction makes the Quality Gate ERR trap report `BASH_LINENO[0]` with a `LINENO` fallback. The complete hosted-acceptance workflow test file passed locally (58 tests), and a Bash reproduction reported caller line 11 while the trap handler was at line 5. The exact Administrator assertion `test "$(sudo -n id -u)" = "0"` remains required and asserted; privilege checks were not weakened.

Remote `main` readback matches `a381b65d275d458b871930f0c76091e2b633c7a2`. All six required post-merge push workflows succeeded: CI (40569054029), Codex CI (40569054122), Docker Image (40569054067), Required Quality Gate (40569054146), Docs Deploy (40569054510), and Invariant Tests (40569054375). Nightly Self Check (40569054105) succeeded; Forge Smoke (40569054499) was skipped by condition. Source preflight returned `correct_remote_and_local_base`. Custody verified all 889 predecessor sequences before this append.

Evidence record: `work/construction/evidence/0890-integrate-pr-2969-main-verification.json`
