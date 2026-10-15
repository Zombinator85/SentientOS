# Sequence 242 - Resource-linked family outcomes require their preregistered denominator

Resource reconciliation now requires a multi-probe family score to carry the exact probe count from its protocol-bound task descriptor. Missing counts, malformed family denominator metadata, or a mismatched count produce a degraded lineage record with `score_binding_invalid`; the resource receipts and source identities remain visible for diagnosis. The writeback projection retains the expected family probe count and rejects qualified outcome packets that do not match it. Scalar legacy outcomes without a family denominator retain their prior compatible representation.

The adversarial fixture rehashes a family run after removing both score counts. Reconciliation no longer treats that incomplete evidence as a qualified owner-bound score. Existing complete developmental-history and model-replacement resource lineage still passes.

Validation: resource lineage and model-replacement resource tests passed (2 passed); changed source and test modules compiled; `git diff --check` passed.

Next: finish incomplete-outcome admission across model-replacement family outcomes, then connect qualified resource history to a distinct bounded computational recommendation and verify later selection after restart.
