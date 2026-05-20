# Codex Validation and Landing Contract

## Required validation posture for system tasks
Run the relevant validation matrix/check chain before final reporting. A subsystem landing is incomplete without matrix evidence.

## Continue-after-failure behavior
If a command fails, continue running remaining feasible commands to produce full diagnostics.

## Failure classification categories
Classify each failure as one of:
- caused by this task,
- pre-existing,
- external dependency,
- environment/bootstrap.

Fix failures caused by this task before declaring completion.

## Docs bootstrap/recheck expectations
When docs dependency checks fail, run docs bootstrap, re-run dependency checks, then run docs build.

## Mypy baseline impact reporting
Report baseline result and any ratchet impact; do not weaken/suppress the baseline contract.

## Matrix runner reporting expectations
Report matrix summary status, required-failure set, and output artifact path when generated.

## Final report expectations
Include command-by-command results, classifications, fixes, and unresolved risks.

## Completion rule
"Feature exists but full matrix not run" is not a completed landing for a system task.
