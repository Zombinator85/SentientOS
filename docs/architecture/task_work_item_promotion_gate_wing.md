# Task Work Item Promotion / Execution Readiness Gate Wing

`sentientos/work_item_promotion_gate.py` and `scripts/evaluate_work_item_promotion.py` provide a metadata-only readiness gate that consumes a completed dry-run review packet and returns a deterministic promotion dossier.

## Boundaries
- Reads supplied JSON evidence only.
- Does not invoke intake, handoff, dry-run adapter, dry-run closure, or workspace lifecycle helpers.
- Does not execute, rollback, mutate workspace targets, or call subprocess/shell/network/provider/prompt paths.
- Optional artifact writing occurs only when caller supplies `--output`.

## Promotion outcomes
- `promotion_ready_for_admission_review`
- `promotion_ready_with_warnings`
- `promotion_requires_manual_review`
- `promotion_requires_clarification`
- `promotion_blocked_authority`
- `promotion_contradicted`
- `promotion_insufficient_evidence`
- `promotion_failed`
