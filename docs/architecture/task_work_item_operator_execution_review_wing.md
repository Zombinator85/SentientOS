# Task Wing: Operator Execution Review Packet

This wing consumes accepted operator-confirmed preflight metadata and produces an operator-facing execution review packet.

## Boundaries
- Metadata-only execution review packet generation.
- Deterministic checklist and optional manual command candidate.
- No execution, verification replay, lifecycle closure/orchestration, rollback, cleanup, scheduling, or agent execution.

## CLI
`python scripts/build_operator_execution_review.py --preflight-run <preflight_run.json> --proposal <proposal.json> --summary`
