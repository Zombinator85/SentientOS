# Task Work Item Lifecycle Dry-Run Adapter Wing

## Scope
- `sentientos/work_item_lifecycle_dry_run_adapter.py`
- `scripts/run_work_item_dry_run.py`
- `tests/test_work_item_dry_run_adapter.py`
- `tests/test_run_work_item_dry_run_script.py`

This wing bridges normalized work-item intake + lifecycle handoff planning to a bounded lifecycle rehearsal. It is dry-run only and metadata-only.

## Behavior
- Consumes supplied normalized work-item packet JSON and handoff plan JSON.
- Runs eligibility checks.
- Invokes `run_workspace_change_set_lifecycle_orchestration(..., mode="dry_run_full_lifecycle")` only when all checks pass.
- Never invokes execution lifecycle modes, never calls workspace file effect helpers directly, and never reads target files.
- Supports optional explicit caller-supplied adapter artifact write.

## Reviewer proof + capability posture
The reviewer proof bundle documents this capability via `work_item_lifecycle_dry_run_adapter_capability` and does not run it by default. Capability registry marks this dry-run adapter as implemented while full execution/scheduler/live tracker integration/agent execution/network/provider/prompt/workspace execution/PR-issue mutation remain blocked or deferred.
