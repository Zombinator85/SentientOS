# Sequence 244 - Work-run recovery binds the complete plan identity

The goal executor used a plan identifier derived from creation time, goal graph, and allocation, while persisted run validation compared only task IDs and kinds. A reused plan ID could therefore conceal changed commands, dependencies, costs, preconditions, or omissions and replay prior completion evidence against a different plan.

Work plans now expose a canonical full-definition digest. Work-run IDs and schema-v2 run artifacts bind to that digest; the executor persists and reloads only the exact plan identity. Changed plans use a separate immutable path, and an encountered legacy unbound artifact fails closed rather than being treated as reusable completion evidence. No command or effect authority is added.

The adversarial test changes command, dependency, and cost fields while retaining plan and task identifiers, and verifies that recovery does not reuse the old run. Exact-plan recovery and task non-reexecution remain covered.

Validation: work-plan loading, executor recovery, goal-state, progression, and plan tests passed (36 passed); changed Python sources/tests compiled and `git diff --check` passed.

Next: continue the dependent task progression chain with fresh-process outcome selection, then resume qualified resource-informed recommendations and epistemic revision.
