# Sequence 221 — Preserve repeated-block evidence in strategic proposals

Strategic adaptation now groups blocked goal outcomes by their stable reason instead of the serialized reason-plus-evidence string. That makes repeated causes visible when different goals cite different evidence paths. The proposal records the affected goal IDs, supporting evidence paths, and the posture `executor_recorded_not_independently_verified`. Priority recommendations target enabled goals actually listed as blocked, while protected goals remain excluded; the proposal remains approval-gated.

Validation: 9 strategic adaptation, goal progress, and goal-state tests passed. Both affected Python files compiled and `git diff --check` passed. A fixture with two distinct evidence paths verifies stable grouping, preserved provenance, and that only the eligible blocked goal receives the recommendation.

This consumes persisted executor state as a planning signal. It does not assert independently verified task consequences or grant automatic strategic change authority.
