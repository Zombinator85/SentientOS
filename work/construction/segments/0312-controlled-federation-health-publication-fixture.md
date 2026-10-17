# Sequence 312 — Add a controlled changed-output Federation Health publisher fixture

PR #2307 added an opt-in workflow_dispatch fixture for the existing Federation Health publisher. It labels the generated document TEST FIXTURE — NOT TELEMETRY, uses a unique run-specific branch, and verifies by GitHub readback that the resulting draft PR targets main and changes only docs/FEDERATION_HEALTH.md. The generator and fixture jobs retain contents: read; only the dependent publisher has contents/PR write. Cleanup closes the exact fixture PR without merging, deletes the unique branch, reads both back, and uploads a proof artifact including cleanup failures.

The ordinary post-merge path executed successfully after the merge. Run 39048224084, event push, source ef64fc693ec2c20bda2f0a68a6ad249c8e3db88d, completed successfully. The hosted Administrator preflight and generator passed; output was one node, zero recent events, quiet. Artifact 12106528170 (223 bytes) had GitHub digest sha256:3d85746d3828bd80bbdae3aa912cdea527218f0098341c7751b104cb82ca1949. The dependent publisher downloaded the same digest and reported pull-request-operation none because docs/FEDERATION_HEALTH.md was unchanged. Main Required Quality Gate 39048224021 passed.

PR #2307 merged by regular merge as ef64fc693ec2c20bda2f0a68a6ad249c8e3db88d, tree e675499dfd9f94c21fffeee1b309b29d8ce2da9a. Final candidate 951fc71e4082356c23c4a87d5cb2b24bddbbaaa7 passed CI 39047656777, Required Quality Gate 39047656768, Lint 39047656828, Docker 39047656767, Invariant Tests 39047656783, Codex CI 39047656776, Release 39047656812, and Gradient null regression 39047656803. The first hosted Quality Gate attempt after a title update failed because its immutable event payload retained the earlier PR title; the title was aligned before a fresh push, whose finalizer passed. A duplicate fixture-proof upload step was discovered and removed, with a regression assertion. Local YAML and embedded-script validation passed; the existing workflow contract and new fixture safety/cleanup tests passed (2 tests).

The fixture dispatch itself remains unexecuted. The connected GitHub API exposes no workflow_dispatch operation, so this increment proves the safe path is implemented and validates the normal post-merge execution, but does not claim a changed-output PR was created. Operator action required: on GitHub Actions, run Federation Health Update with publication_fixture=true, then retain the generated fixture-publication proof artifact. No production telemetry was fabricated or altered.

The optional "invite" workflow also completed with failure (run 39048223891): its GitHub token received 403 "Resource not accessible by integration" while attempting a comment. This is not a required integration check; no extra issue-write permission was granted for the greeting.

Sequence 286's nine known and one unidentified unrecoverable payloads remain unresolved. The sequence-178 workspace remains untouched.

Verified source commit: ef64fc693ec2c20bda2f0a68a6ad249c8e3db88d
Verified source tree: e675499dfd9f94c21fffeee1b309b29d8ce2da9a
Previous segment SHA-256: 56acc2e12b29f1d326172c61080fc69f04b785e9268e5916fb2e48e55218a4b3
