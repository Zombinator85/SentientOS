# Codex Narrow Repair Task Template

Narrow repairs are exceptional. Use only when:
- the user explicitly asks for a surgical patch,
- the failure is localized and blocking,
- or a blocker prevents larger system work.

## Goal
Describe the exact defect and desired patch scope.

## Failure reproduction
Document the exact command(s), error text, and preconditions.

## Exact files changed
List only files touched by the repair.

## Focused tests
Run targeted tests that prove the localized fix.

## Baseline/matrix/docs impact statement
State whether mypy baseline, matrix lanes, and docs are impacted. This template must not be used to defer task-caused subsystem fallout that belongs in a whole-system landing.

## Safety constraints
No authority widening, no runtime boundary expansion.

## Done when
The localized failure is reproduced, fixed, and proven by focused tests with no unintended scope expansion. It does not supersede whole-system requirements unless the repair is explicitly scoped as narrow by the user or justified as pre-existing/external/environmental fallout.

## Commit/report rule
Do not fabricate a commit if no code or docs changes are required.
