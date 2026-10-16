# Sequence 228 — budget-constrained task omission evidence

The clean recovered source tree exposed a planning gap: GoalExecutor enforced cumulative risk and throughput budgets, but silently dropped tasks that exceeded either limit. Planning now emits deterministic TaskOmission rows carrying the affected goal, task kind, and the specific exceeded budget. Unsupported-task omissions remain intact.

Validation: 36 focused goal-execution, plan-load, journal, state-update, and orchestrator tests passed. The two affected files compiled and targeted diff checking passed. Pytest used the repository's explicit naked-pytest opt-in because the canonical editable install could not bootstrap setuptools through the unavailable proxy.

Recovery provenance: based on verified ancestor 5195beadb32a199ae362c248357c6d39d80fd576 (tree 45f2f2b6928de5bedc9fe31ed0126bab509ac89e); hydrated 136 changed paths from the exact GitHub target tree, verified all 136 Git blob IDs and modes, and reconstructed root tree 0ea8c9e8b385ad05cdc81e8057e811fe4354bef0. The local recovery commit is synthetic and is not represented as the upstream commit.

Next: inspect whether retained, qualified resource experience can condition a later bounded proposal without granting allocation authority.
