# Operator Lifecycle Closure Review Wing

Builds deterministic, metadata-only closure review packets from operator-confirmed verification evidence.

CLI:
`python scripts/build_operator_lifecycle_closure_review.py --verification-run <verification_run.json> --proposal <proposal.json> --summary`

This wing is review only and does not invoke lifecycle closure, orchestration, rollback, or cleanup.
