# Active construction checkpoint

Sequence 228 makes finite task-budget decisions visible. GoalExecutor now records a TaskOmission for each generated task excluded by cumulative risk or throughput limits, retaining goal/task identity and the exceeded budget reason. Unsupported-operation omissions remain present.

Latest source commit: 38c39a6b6a06da6516002794bef982486a4fd07f
Latest source tree: fe50e419825063ef46762ffdc6287f489784e90c
Latest segment: work/construction/segments/0228-budget-task-omission-evidence.md
Evidence: work/construction/evidence/0228-budget-task-omission-evidence.json
Sequence: 228

Validation: 36 focused goal executor, dependency, goal-state, plan-load, journal, and orchestrator tests passed. Two changed files compiled and targeted diff check passed. Tests used the explicit naked-pytest opt-in because canonical editable-install bootstrap required unavailable setuptools through the blocked proxy.

Recovery: local clean clone from ancestor 5195beadb32a199ae362c248357c6d39d80fd576; 136 changed paths hydrated and each blob identity verified. Reconstructed root tree exactly matched 0ea8c9e8b385ad05cdc81e8057e811fe4354bef0. Local commit c75885ee is a synthetic recovery snapshot, not the upstream commit. Original stale checkout was left untouched.

Next: inspect the bridge from admitted resource-consumption history into later bounded resource/goal proposals. Existing observation and retention paths are already composed; find a concrete decision-flow gap before implementing.
