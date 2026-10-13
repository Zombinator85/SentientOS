# 0091 — Preserve historical self-model semantics into later cognition

Source baseline: `00ddc4b0f56ac9c991111a5cf4a870e855bef8fb`, tree `fc1cbe0524eba1ea6a643944f59de770de68763e`. The self-model's N+1 projection previously omitted claim category, lifecycle stage, temporal scope, source observation timestamps, interpretation, current-truth, and the claim authority map. Status and freshness alone were insufficient to preserve the source owner's exact semantic qualifiers at the cognition boundary.

The projection now retains those fields with each claim. Up to 16 source observation timestamps are projected with their total count, full-vector digest, and explicit complete/prefix posture; the enclosing claim semantic digest still binds the full durable claim. A fresh owner in a later tick receives `historical_interpretation`, historical status, unknown freshness, the source observation time, interpretation=true, current_truth=false, and all-false authority. Same-tick access remains unavailable.

Six focused developmental modules passed **151 tests, 0 failed, 0 skipped**. Changed Python compiled and `git diff --check` passed. Evidence: `work/construction/evidence/0091-self-model-historical-semantics-cognition-junit.xml` and `work/construction/evidence/0091-self-model-historical-semantics-cognition-results.json`.

Seq90 hosted Source Validation succeeded; docs, invariants, and self-check failed at existing environment/privileged gates; Helm was still running at the last query. No runtime or authorization behavior was activated. All construction remains unverified for production; actual model acquisition/transfer remains blocked by unavailable model bytes and exact commissioning/operator approval.

Next: continue examining downstream developmental writeback and task-scoring consumers for whether historical self-model interpretations remain separate from authored developmental lessons; keep fixture outcomes distinct from live-model behavior.
