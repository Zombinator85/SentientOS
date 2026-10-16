# Sequence 225 — Reconstruct terminal task outcomes from the journal

Work-plan journal schema v2 stores the complete terminal `TaskRun` alongside status and reason, including the original timestamps, duration, destructive posture, and artifacts. A restarted executor reconstructs terminal task results without rerunning the task and returns the same run artifact under the same write-once identity. Schema v1 journal rows remain readable; a start without a terminal result remains explicitly unknown.

Validation: 34 focused executor, dependency-plan, goal-state, journal, plan-load, and orchestrator-goal tests passed. Four affected Python files compiled and `git diff --check` passed. Tests verify exact replay, one command invocation, one persisted work-run pulse row, v1 journal compatibility, and dependency/interruption behavior.

