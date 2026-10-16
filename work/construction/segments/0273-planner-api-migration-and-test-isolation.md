# Sequence 273 — Planner API migration and test isolation

The full hosted CI run for sequence 272 found one source-caused compatibility failure: the adverse historical-outcome cognition test still invoked the removed `GoalExecutor.build_plan` method. Planning now belongs to `GoalPlanner`; the test was migrated to that canonical API without restoring planning on the executor. The exact failure test passes locally, and all 93 tests in the resident developmental cognition module now pass.

The same local module initially had ten sandbox-only failures because default global runtime governance attempted to create `/glow` in a read-only filesystem. Its shared governor, runtime, and federation roots are now set to each test's pytest temporary root. Assertions and execution coverage are unchanged; the isolated module passes 93/93.

Sequence 272's Required Quality Gate passed on GitHub Actions. Its strict audit wrapper reported UID 0, `passed`, source tree `c0793416a0a2e71d6336ff9c7bb6c7587baa6bbc`, and the exact PR merge commit. The workflow artifact retained the privileged report and strict audit outputs. The PR runner independently checked out and measured that same tree. Seven new source/evidence blobs for sequence 272 read back with matching byte counts and SHA-256 digests.

The sequence 272 CI run also recorded success for Lint Benchmark (all matrix entries), Docker, Codex CI, Invariant Tests, Release validation, Gradient null regression, self-check, Helm, and docs link checking. The source-validation job failed only on the stale planner API call described above. The lifecycle acceptance node verifier was skipped after that command failed; the exact local task acceptance remained 17/17. This failure and repair are kept as separate append-only evidence.

