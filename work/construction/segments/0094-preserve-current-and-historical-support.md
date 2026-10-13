# 0094 — Preserve current and historical support for equal claim values

Source baseline: `0875133bb896cd78c3efbd6483e7cceca50fd254`, tree `5de3332642332c03569ed2a448aa76ab6a49b75d`. The reconciler grouped claims by value and used the first supporting fact's category. When one current source and one historical source agreed on the same subject/predicate/value, one category could absorb the other depending on fact iteration order.

Grouping now keys support by both canonical value and category while computing contradiction only across distinct values or explicit World-State conflicts. The same observation supported by a current source and a historical transition source therefore produces separately attributable `current_state` and `historical_interpretation` claims, with their own source evidence identities and statuses. Equal support is not mislabeled as contradiction, and reversed input order yields the same result.

Two focused self-model modules passed **30 tests, 0 failed, 0 skipped**. Changed Python compiled and `git diff --check` passed. Evidence: `work/construction/evidence/0094-current-historical-claim-grouping-junit.xml` and `work/construction/evidence/0094-current-historical-claim-grouping-results.json`.

This preserves evidence categories; it does not make either claim authoritative or establish model learning. Production remains unverified.

Next: inspect contradiction and supersession reconciliation when values conflict across current and historical support, ensuring the retained lineage shows both value-level conflict and each source category without latest-wins.
