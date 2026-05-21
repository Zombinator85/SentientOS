# Codex Validation and Landing Contract

## Required validation posture for system tasks
Run the relevant validation matrix/check chain before final reporting. A subsystem landing is incomplete without matrix evidence. The full relevant matrix must run after the final task-caused code/doc/test change.

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
Include command-by-command results, classifications, fixes, and unresolved risks. Do not create PR metadata or final done-reporting before the post-final-change full matrix run completes.

## Completion rule
"Feature exists but full matrix not run" is not a completed landing for a system task.

## Finalization order (system tasks)
Required order is strict:
1. Make the final task-caused code/doc/test change.
2. Run the full relevant validation matrix and address task-caused fallout in the same task.
3. Only then produce final report and PR metadata.

Follow-up stabilization PRs for task-caused fallout are a failure mode, not expected workflow.

## Non-compliant statements and outcomes
The following are non-compliant for system tasks:
- "Feature exists but full matrix not run."
- "If you want, I can run the full matrix now" after creating PR metadata or done-reporting.
- Deferring task-caused matrix fallout to a follow-up stabilization PR.

Tiny stabilization diffs are acceptable only for pre-existing, external dependency, or environment/bootstrap issues, or when the user explicitly requested a narrow repair.
