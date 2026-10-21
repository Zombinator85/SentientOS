# Sequence 526 — reconcile sequence 525 stage-approval timezone fix

PR #2535 merged regularly as `47ea84a0f0ecd91fac886687a43c47093f724da3`, tree `492425c3eb5dab4305d52a2ad0ef3dc3b9a799b4`, preserving ordered parents `90f5d412709838b75470c3172fa84067af3c3035` and `e0cb09da3ac990ed794e6311196ca0cfd4d41ceb`. The two-commit candidate rejects RFC 3339 `-00:00` in either stage-approval validity bound before journal or stage effects. The hosted regression initially exposed that pytest records parameter cases under expanded IDs; stable case IDs were added to both workflow selection and acceptance, and the exact two cases then passed acceptance. A subsequent pre-commit attempt exposed the repository rule requiring PR title and latest commit subject to match; the title was aligned, and the final actual-Administrator Quality Gate, pre-commit reconstruction, finalizer, and separate metadata guard all passed.

Local verification passed the affected transition module (40 tests), focused workflow-binding and timestamp regressions (3 tests), exact two-case task acceptance, targeted mypy, compilation, and diff checks. Hosted candidate push and PR CI, source validation, full lint matrix, build, Docker, Helm, invariants, CPU smoke, and Quality Gate passed. Post-merge CI, source validation, self-check, docs linkcheck, build, Docker, deployment, Helm, CPU smoke, invariants, Quality Gate, and Codex CI all passed; Forge Smoke was skipped by condition.

Nightly Audit Integrity #39572356700 passed on exact main `47ea84a0…` with its repair job skipped. Federation Health has not yet run on this main SHA; its latest scheduled success remains #39546186159 on older `7fbd149ddb0f48f2385c18590c254a64cc2522bd`. Automated Federation Health PR #2511 remains open and unverified. No production transition, activation, serving, inference, or writeback was performed.

Latest verified main: `47ea84a0f0ecd91fac886687a43c47093f724da3`, tree `492425c3eb5dab4305d52a2ad0ef3dc3b9a799b4`
Latest construction segment: work/construction/segments/0526-reconcile-sequence525-stage-approval-timezone-fix.md
Sequence: 526 (verified reconciliation)
