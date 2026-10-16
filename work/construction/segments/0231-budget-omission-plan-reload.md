# Sequence 231 - Budget omission plan reload

The persisted work-plan loader now accepts the deterministic budget omissions introduced in seq228. `risk_budget_exceeded` and `throughput_budget_exceeded` are bound to the executable task kinds that the goal planner emits; `task_kind_not_implemented` remains limited to `fetch` and `doc_update`. Unknown or mismatched reason/kind pairs still fail closed.

Validation: all 38 focused goal planning, plan load, execution journal, goal run/state, and orchestrator execution tests passed. The changed module and two test modules compiled; `git diff --check` passed. The explicit test opt-in was used from the exact recovered source tree.
