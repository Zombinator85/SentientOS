# Sequence 267 - Bind explicit target applicability to planning identity

Added one shared proposition applicability rule for allocation and plan construction. A task-family proposition now requires an exact family tag, a well-formed protocol-bound source model identity digest, and a separately observed target identity digest whose observation timestamp exactly equals the plan creation timestamp. Missing, stale, malformed, or changed target identity remains deferred as `epistemic_applicability_unresolved`; the executor applies the same fail-closed rule even to a manually constructed allocation.

The plan identity now binds the epistemic projection digest, full review scopes, target identity observation and timestamp, goal tags and applicability outcomes, allocation deferrals and reasons, task omissions, prior-run digest, and no-replay outcomes. Unrelated goals remain eligible. No history is deleted and no model identity is inferred from a goal tag.

Validation: 35 selected pytest cases passed across applicability, allocation, plan construction/execution, task-family staging, progression after restart, preregistered history comparison, and history comparison with invariant self-model/epistemic bindings. Python compilation passed. Two wider world-state recovery tests could not complete because their child processes attempt to create `/glow/governor` on the read-only sandbox. An additional partial-score downstream-cognition test fails at the existing bounded selected-evidence admission (`selected_evidence_unbounded`); it is recorded for follow-up because it is outside this increment's changed paths.

The integrated fixtures remain deterministic and simulated. No live inference, learning, production effect, authority expansion, or history removal is claimed.
