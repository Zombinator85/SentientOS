# Sequence 664: Integrate PR 2765 post-merge verification

PR #2765 merged normally as `46cabb0dbb4a5230c29477702c319e49b2985353`, with verified main `0dcdd523144e6182fef1e80dc66cbd03055b2e41` as first parent and candidate `1033f8850a0033c6a6338306b320541698ffafc8` as second parent. Main tree `239b673d680b720ae549d7f8b2f854316ce474a` matches the exact candidate tree.

Sequence 663 documented the component-aware readiness output-root ancestry rule. Its local repeat full regression did not complete and was stopped without a result. Exact-head hosted CI source validation and documentation link checking passed, along with exact acceptance, hosted privileged finalization, PR metadata guard, and all applicable PR workflows. The post-merge Required Quality Gate, CI, Invariants, Docker, Codex CI, and Docs Deploy passed. Forge Smoke was skipped by workflow condition. The main Quality Gate artifact SHA-256 is `8a671fde2be04a8667ef493c033ba6a33efe7b78ea97ac58ba4eee9ad7904bdb`.

Fresh source preflight observed clean remote main at `46cabb0dbb4a5230c29477702c319e49b2985353` with tree `239b673d680b720ae549d7f8b2f854316ce474a`. Construction custody verified the 663 preceding segments before this record.

Evidence: `work/construction/evidence/0664-integrate-pr-2765-main-verification.json`.
