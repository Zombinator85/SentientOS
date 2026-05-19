# Task Work Item Lifecycle Handoff Planner Wing

The SentientOS Work Item Lifecycle Handoff Planner is a metadata-only bridge from a normalized intake packet to a bounded recommendation for the next governed lifecycle surface.

## Scope

Implemented surfaces:
- `sentientos/work_item_lifecycle_handoff.py`
- `scripts/plan_work_item_handoff.py`
- `tests/test_work_item_lifecycle_handoff.py`
- `tests/test_plan_work_item_handoff_script.py`

This handoff wing:
- reads a supplied normalized work item packet JSON,
- validates required packet metadata and classifies readiness,
- emits a deterministic handoff plan and next-surface classification,
- can emit metadata-only lifecycle orchestration request candidate data **only when explicit workspace proposal metadata already exists**.

This handoff wing does **not**:
- invoke lifecycle orchestration,
- invoke admission/preflight/execution/verification/closure,
- create workspaces/branches/PRs,
- call network/provider/prompt/subprocess/shell/agent/scheduler surfaces.

## Suggested command

`python scripts/plan_work_item_handoff.py --packet <normalized_work_item_packet.json> --summary`
