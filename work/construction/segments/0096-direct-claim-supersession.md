# 0096 — Link all direct claim predecessors through conflict resolution

Source baseline: `e7247044171958b2fd338d98fb4451e242822600`, tree `f5f1ffa6ae37145eacaf5e8cdea3dff5d712f999`. The mixed current/historical conflict was preserved, but recovery to an unambiguous state could retain only one predecessor because reconciliation indexed active claims by claim key in a single-value map.

Longitudinal reconciliation now retains every current, contradicted, and unresolved predecessor for a claim key. Successor claims link every predecessor whose value, temporal category, or evidence identity changed. When prior support disappears, its `superseded_by` list contains only claims that explicitly reference it. Matching value/category claims retain their original first-supported generation.

Regressions cover resolution of a mixed-category conflict, direct successor links, retained historical source attribution, and replacement of source support for an unchanged proposition. The focused longitudinal and later-cognition modules passed **33 tests, 0 failed, 0 skipped**. Both changed Python files compiled; `git diff --check` passed. Evidence: `work/construction/evidence/0096-conflict-resolution-supersession-junit.xml` and `work/construction/evidence/0096-conflict-resolution-supersession-results.json`.

This verifies deterministic fixture reconciliation and persistence semantics, not model performance or production behavior. Production remains unverified.

Next: inspect the scorer and history-intervention contracts to determine whether task-level correctness evidence can be joined to durable trial recovery without changing frozen protocols or manufacturing actual-model results.
