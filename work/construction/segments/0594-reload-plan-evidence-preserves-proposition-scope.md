# Sequence 594 — reload and cross-proposition evidence boundaries

PR #2645 extends the retained-experience path through durable plan evidence recovery. The regression now reloads the persisted evidence using `load_work_plan_evidence` and compares the full payload with the originally persisted canonical JSON. It also checks that the evidence retains the plan's allocation artifact digest.

Before applying valid positive support, the same scenario registers a distinct task-family proposition and a support binding owned by that proposition. Attempting to update the original proposition with the foreign binding must raise `candidate_evidence_missing_foreign_or_withdrawn`. The existing test continues to cover receipt verification after restart, exact model identity, positive and adverse history, and the non-executing planning boundary. No production behavior, inference, or authority was changed.

The exact source candidate is `9edb578344eebb85f96ae64ea7168fb690e4c6d3`, tree `4231ebb733ed10ebdffeb573670197e3e7c90b45`, based on verified main `965659041bc448ba3d3166d7e618ef255abf0387`. The complete pytest suite passed in CI and Lint Benchmark. Source validation passed the integrated resource-to-cognition lifecycle and canonical planning/execution separation.

All eight exact-candidate workflows passed: CI 39855209957, Required Quality Gate 39855209871, Release 39855209989, Codex CI 39855209827, Gradient null regression 39855209826, Invariant Tests 39855209754, Docker Image 39855209833, and Lint Benchmark 39855209707. The required gate passed Administrator audits, exact acceptance binding, audit immutability, hosted finalization, and the separate pre-publication metadata guard.

PR #2645 merged normally as `c79b84f7fcaf1ab484cd7157f61666edf9016e45`. The merge commit has the candidate tree `4231ebb733ed10ebdffeb573670197e3e7c90b45`, with candidate as its second parent; the merge introduced no tree changes beyond the tested candidate. No production goal execution or model inference occurred.

Sequence: 594 (verified source integration)
