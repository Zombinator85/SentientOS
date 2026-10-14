# Sequence 227 — legacy process-boundary recovery

The recovery check now crosses a real child-process boundary. It starts from a legitimate version-1 terminal journal and its pre-existing write-once run artifact. The child process prohibits task execution, then confirms the recovered run and artifact path remain identical and the journal pulse count stays at one.

Validation completed before publication: 36 focused executor, dependency, goal-state, journal, plan-load, and orchestrator tests passed. Six affected Python files compiled; targeted `git diff --check` passed.

This closes the legacy restart case for the bounded work-run recovery path. Fixture-only; no production execution or additional effect authority.
