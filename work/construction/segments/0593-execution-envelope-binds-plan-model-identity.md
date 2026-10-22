# Sequence 593 — execution envelopes must match verified plan model identity

PR #2643 closes an identity gap between canonical planning and execution. The executor already loads and verifies the immutable work-plan evidence and checks its allocation binding, but it did not compare the evidence's target model identity and observation time with the execution envelope. The change now rejects either mismatch with `work_plan_execution_model_identity_binding_mismatch` before opening the execution journal.

The regression first produces a plan from receipt-verified, model-v1 support. It supplies an execution envelope naming model v2 and directly exercises the original executor method while the planner's execution sentinel remains active. The executor rejects the mismatch, and no run artifact is written. Matching-identity canonical orchestration remains covered by the integrated lifecycle acceptance.

The first hosted candidate `0d92efa2bc253da6d9933de8998e3939cbc958c9` exposed two fixture issues before the final candidate: a PR-title race caused the initial strict-gate preflight to observe an old title, and the planning sentinel intercepted the direct executor call. The corrected fixture initially misplaced the captured executor reference, producing a NameError. Both were corrected in append-only child commits. The final candidate is `32c288ccbac879272c9875d7d537b7994a7109d1`, tree `33bce2d4eba059464014021aa0356e4b5e327527`, based on sequence 592 main `b8ce7283837e454a24f127562c11b27403f4ecb7`.

Final-head CI run 39853665217 passed the full self-check, integrated resource-to-cognition lifecycle, and exact canonical planning/execution-separation acceptance. Required Quality Gate 39853672848 passed strict Administrator audits, exact acceptance binding, audit immutability, hosted finalization, and the separate metadata guard. Release 39853665222, Codex CI 39853665289, Gradient 39853665055, Invariant Tests 39853665202, Docker 39853664923, and Lint Benchmark 39853665084 passed. All eight final-head workflows passed. The earlier failed gate run 39853665026 was superseded by the fresh final-head gate after PR metadata was aligned; it did not contribute to the successful acceptance claim.

PR #2643 merged normally as `d4942c0228d46929159fd45aec7e5b0b1abef077`. Candidate-to-merge comparison reported zero changed files and retained tree `33bce2d4eba059464014021aa0356e4b5e327527`. No inference or production transition occurred.

Sequence: 593 (verified source integration)
