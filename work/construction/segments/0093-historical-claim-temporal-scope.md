# 0093 — Give historical interpretations an explicitly historical scope

Source baseline: `fbb8cd504beebc8304c6f4da1d92e8238e07aed5`, tree `2295ebe2858e355ca6670e13f8e4e369c613446a`. The longitudinal self-model marked every claim `temporal_scope=historical_and_current`, including claims with category `historical_interpretation`, status `historical`, freshness `unknown`, and `current_truth=false`. That broadened the apparent temporal scope beyond the evidence category.

New claims now use `temporal_scope=historical` when their source category is historical interpretation; other claim categories preserve the prior scope. Later cognition keeps that exact scope with the other source qualifiers. Existing durable records remain readable under their original content digest and historical meaning.

Two focused self-model modules passed **29 tests, 0 failed, 0 skipped**. Changed Python compiled and `git diff --check` passed. Evidence: `work/construction/evidence/0093-historical-temporal-scope-junit.xml` and `work/construction/evidence/0093-historical-temporal-scope-results.json`.

This corrects semantic scope only; it does not establish current truth, independent evidence, or model learning. Local-model execution remains blocked by absent payload and exact commissioning/operator approval.

Next: verify selected-claim reconciliation behavior when the same predicate/value is supported simultaneously by historical and current sources, so grouping cannot inherit an ambiguous category from input order.
