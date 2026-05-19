# Task Work Item Lifecycle Dry-Run Closure Wing

## Scope

This wing seals completed work-item lifecycle dry-run adapter outputs into a deterministic, reviewer-facing closure manifest. It is metadata-only and non-authoritative.

## Inputs

- normalized work-item packet JSON,
- lifecycle handoff plan JSON,
- lifecycle dry-run adapter result JSON.

## Output

A single metadata-only closure manifest containing compact IDs/digests/statuses/counts and contradiction/missing-metadata findings. Optional explicit caller-supplied artifact write is supported.

## Boundaries

- Does **not** invoke intake, handoff planning, dry-run adapter, or workspace lifecycle orchestration.
- Does **not** execute, verify, close, rollback, or mutate workspace state.
- Does **not** perform network/provider/prompt calls, tracker mutations, branch/PR creation, scheduler action, or agent execution.
- Does **not** read workspace target files.

## Status classes

- `dry_run_closed_clean`
- `dry_run_closed_with_warnings`
- `dry_run_closed_blocked`
- `dry_run_closed_manual_review`
- `dry_run_closed_insufficient_metadata`
- `dry_run_closed_contradicted`
- `dry_run_closure_insufficient_evidence`

## Reviewer surfaces

- Module: `sentientos/work_item_dry_run_closure.py`
- CLI: `scripts/build_work_item_dry_run_closure.py`
- Tests: `tests/test_work_item_dry_run_closure.py`, `tests/test_build_work_item_dry_run_closure_script.py`

The reviewer proof bundle documents this capability and does not run the closure builder by default.
