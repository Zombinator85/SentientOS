# Task Work Item Operator-Confirmed Verification Run Wing

`sentientos/work_item_verification_run.py` and `scripts/run_operator_confirmed_verification.py` provide deterministic, operator-confirmed invocation of the existing workspace change-set verification wing from a completed execution run packet.

## Boundaries
- Verification invocation only.
- Never lifecycle closure, lifecycle orchestration, rollback, cleanup, scheduling, agent execution, or branch/PR/issue mutation.
- No subprocess/shell/network/provider/prompt surfaces.

## Required Inputs
- Execution run packet JSON
- Workspace change-set proposal JSON
- Workspace root
- Explicit `--confirm-verification` operator confirmation

## Output
- Deterministic metadata-only verification run packet and receipt.
- Optional explicit caller-supplied artifact path.
