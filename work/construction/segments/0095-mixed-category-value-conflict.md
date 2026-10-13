# 0095 — Retain contradictory values across temporal categories

Source baseline: `d0f25ec954e97cf4d40262ac5747069be9af1135`, tree `dec93abac28a7bae6f09cbea7d7c5274c787a631`. With current and historical support groups now separate, the remaining check is whether value conflicts retain each category and source rather than applying latest-wins.

A focused conflict fixture supplies current `running` and historical `stopped` dispositions for the same claim key. Reconciliation retains both values with their respective source IDs and categories, marks both `status=contradicted` and `contradiction_state=contradicted`, and keeps `current_truth=false` on both.

The focused longitudinal self-model suite passed **27 tests, 0 failed, 0 skipped**. Test Python compiled and `git diff --check` passed. Evidence: `work/construction/evidence/0095-temporal-category-value-conflict-junit.xml` and `work/construction/evidence/0095-temporal-category-value-conflict-results.json`.

This verifies fixture reconciliation semantics, not truth or model performance. Production remains unverified.

Next: review status transitions when previously contradicted mixed-category claims become unambiguous, ensuring supersession preserves old source lineage and marks current versus historical successors correctly.
