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


## Required-lane repair loop
After any task-caused code/doc/test/config/capability change:
1. Run the required validation matrix.
2. If any required lane fails, inspect failed lane output.
3. Classify each failure as task-caused, pre-existing, or environment/bootstrap.
4. Presume task-caused integration fallout for new subsystem/capability changes until proven otherwise.
5. Fix task-caused failures in the same task.
6. Re-run failed lane(s).
7. Re-run the full required matrix after final fix.
8. Commit and PR metadata are allowed only after required_failure_count is 0, unless remaining blockers are proven pre-existing/environmental and accepted by the repo ratchet flow.

## Mypy baseline doctrine
Do not use raw repo-wide mypy as the landing gate when the repository contract uses targeted mypy plus baseline ratchet. Do not ignore mypy_baseline required-lane failures.


## Codex Landing Supervisor
Run `python scripts/codex_landing_supervisor.py evaluate --title "..." --intended-commit-title "..." --matrix-json-path /tmp/work_item_review_packet_matrix.json --summary` after matrix and PR gate; do not finalize unless decision is `ready_to_commit` or `ready_for_pr_metadata`.
