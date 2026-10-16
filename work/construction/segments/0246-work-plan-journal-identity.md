# Sequence 246 - Execution journals follow exact work-plan identity

Run artifacts now use full plan digests, but the append-only task journal remained keyed by `plan_id`. Reusing a plan ID with changed commands or dependencies could make the new run collide with old journal rows and be rejected as a digest conflict.

Execution journals now use the canonical full plan digest in their own immutable filename. When a legacy plan-ID journal exists, its first row is checked: matching plan history remains active for exact-plan restart recovery; a different digest stays preserved and the changed plan receives its separate digest-keyed journal. Plan identity digest encoding is shared between run artifacts and journals.

The adversarial test records an interrupted task under one plan, changes the command while reusing the plan ID, and verifies the new plan receives a distinct journal without inheriting the old interruption. Existing interrupted-task behavior remains conservative: the prior attempt stays unknown and dependent tasks remain blocked.

Validation: work-plan, executor, goal-state, progression, and plan tests passed (38 passed); changed Python sources/tests compiled and `git diff --check` passed.

Next: continue dependent task progression with fresh-process outcome selection, then resume qualified resource-informed recommendations and epistemic revision.
