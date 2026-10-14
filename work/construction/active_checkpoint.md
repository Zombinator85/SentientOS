# Active construction checkpoint

Sequence 229 preserves the exact-tree fallback used to reacquire source while Git transport is unavailable. The procedure starts from a clean local clone of a verified ancestor, hydrates only compare-reported changed blobs from GitHub Git Data, checks each blob and mode, and requires the complete root tree to match before source work. Its XVI exercise hydrated 136 paths and reconstructed target tree 0ea8c9e8b385ad05cdc81e8057e811fe4354bef0 exactly.

Latest source commit: 38c39a6b6a06da6516002794bef982486a4fd07f
Latest source tree: fe50e419825063ef46762ffdc6287f489784e90c
Latest segment: work/construction/segments/0229-exact-source-recovery-fallback.md
Evidence: work/construction/evidence/0229-exact-source-recovery-fallback.json
Sequence: 229

Seq228 validation: 36 focused goal executor, dependency, goal-state, plan-load, journal, and orchestrator tests passed; two changed files compiled and targeted diff checking passed. A separately targeted embodiment suite and admitted-consequence integration test passed 31 tests. Pytest used the explicit naked-pytest opt-in because the canonical editable install needed setuptools unavailable through the blocked proxy.

Next: inspect whether admitted resource consumption and task outcome history can lawfully influence a later proposal. Current linked fixtures record one call unit per inference and explicitly keep CPU/GPU attribution unknown, so do not infer a resource-efficiency gain from them. Continue across the next source-backed architectural region after this review.
