# Sequence 506 — bind stage approvals to signed transition requests

The authenticated live transition ingress now checks that the stage approval names the same requested stage, correlation ID, and operation ID as the exact Ed25519-authenticated request. It also requires the packet’s approval ID and approval digest to identify the same approval. A mismatch is rejected before subordinate verification or controller advancement.

The live rehearsal already constructs matching request and approval identities. Two explicit negative regressions now prove that correlation or operation mismatches produce a rejected, effect-free receipt. The CI source-validation job runs both exact test nodes and includes them in the transition receipt acceptance manifest.

Supplemental local verification passed 83 tests across the transition operator, transition experiment, daemon composition, and hosted-workflow contract suites. Compilation, workflow YAML parsing, `git diff --check`, and targeted Mypy passed. The local repo-wide Mypy baseline helper could not run because its sanitized environment cannot import the sandbox’s user-site Mypy installation; this result is not represented as a pass. Exact-candidate hosted verification remains pending.

No production transition, activation, serving, inference, or writeback was performed. Operator signature validation, issuer binding, subordinate approvals, and separate activation/serving authorities remain in force.

Latest verified main source: `1a568708d31201885034a51b66319b770584b5d4`, tree `3aa51733ce35955a5e0efb51da3ecf06c94a0834`
Implementation source commit: `94046e6bb78d921f5c5bdc468440b620e1c773b2`, tree `870666fbb3454e5ce51699b3f512b7ea85c27dd8`
Latest construction segment: `work/construction/segments/0506-bind-stage-approval-to-signed-transition-request.md`
Sequence: 506 (candidate pending hosted verification)
