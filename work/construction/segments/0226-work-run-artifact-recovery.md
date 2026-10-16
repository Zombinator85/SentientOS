# Sequence 226 — Validate existing work-run artifacts before replay

The executor now checks for the deterministic write-once run artifact before resuming tasks. The loader opens a bounded regular file without following symlinks and validates canonical serialization, plan/run identity, task order and kinds, status consistency, reason stack, and effective destructive classification. When present, journal terminal states must agree and any v2 full task result must match. Invalid or substituted artifacts fail closed before task execution. This preserves recoverability when older v1 journals lack full result details.

Validation: 36 focused executor, dependency, goal-state, journal, work-plan, and orchestrator tests passed. Six affected Python files compiled and `git diff --check` passed. Tests verify exact recovery, single execution, write-once persistence, legacy journal parsing, artifact substitution rejection, and prerequisite failure closure.

