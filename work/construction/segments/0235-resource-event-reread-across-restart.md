# Sequence 235 - Resource event reread across restart

Added a regression at the resource-ledger to World-State boundary. Reprojecting a completed allocation after reconstructing the ledger preserves the ledger and receipt identities and the semantic record digest, while retrieval timestamps change independently. Snapshot counts and remaining call allowance stay unchanged, so reread does not debit completed consumption again.

Validation: 18 resource allocation, strategy-lineage, model-replacement lineage, and process-generation tests passed with one existing skip. The new test passed, compiled, and `git diff --check` passed. This validates existing source behavior; it makes no new production or model-backed claim.

Next: exercise malformed and incomplete resource outcomes through developmental admission, then test a distinct later task where bounded resource evidence can change a computational recommendation.
