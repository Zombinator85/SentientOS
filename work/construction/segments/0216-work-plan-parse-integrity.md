# Sequence 216 — Reject malformed persisted plans

The version-1 work-plan loader previously coerced values and skipped malformed task rows, allowing a corrupted plan to become a different runnable subset. It now validates the persisted envelope and each task before constructing a plan, rejects duplicate task IDs and unselected goal references, preserves exact field types, and rejects disagreement between task kind, mutation precondition, and destructive classification. Valid version-1 plans continue to round-trip.

Validation: 17 work-plan, goal executor planning, execution, and goal-state tests passed. Changed modules compiled and diff check passed. The parser does not add new task kinds or effect authority.
