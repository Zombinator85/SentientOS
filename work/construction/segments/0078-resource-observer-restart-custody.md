# 0078 — Exercise read-only resource observation recovery

Based on freshly verified branch commit `323a8f1d5d7873ac6b51daf1f93f42ab494f4996`, tree `ebfd55c65686cd88a26aa0abdb953c9293c2b35e`. No production source changed.

Added two focused recovery controls for the existing installation-scoped resource observer. The positive case issues the legitimate fixture bundle, uses the existing single-writer owner to durably record one provisional attempt, closes that owner, and then observes through the fixed installation read-only view. Repeated observations and a newly opened observer produce the same manifest identity and canonical ledger snapshot; the attempt remains bound to the same allocation and the published ledger bytes remain unchanged. The observer itself exposes no writer balance API, so assertions use only its immutable canonical snapshot.

The negative/recovery case truncates the ledger and then removes it. The observer reports `resource_ledger_invalid` and `resource_ledger_missing`, respectively. Restoring the exact original bytes permits recovery of the unchanged allocation with zero attempts. The focused suite passes **2/2**. JUnit and canonical test-run provenance are preserved alongside the result summary.

This establishes bounded local fixture behavior for the read-only handoff; it does not establish cross-process production observation, real resource use, or production acceptance. Work remains unverified for production.

Hosted checks were independently fetched for sequence 77: Source validation and helm-k8s-test succeeded; docs, invariants, and self-check failed. This distinction is preserved in `work/construction/evidence/0078-hosted-checks-seq77.json`; hosted source success is not full acceptance.

Next: inspect the next source-backed developmental experiment dependency. Real-model acquisition/transfer performance remains gated on an operator-commissioned model artifact and exact valid approval; do not substitute deterministic fixture results for that demonstration.
