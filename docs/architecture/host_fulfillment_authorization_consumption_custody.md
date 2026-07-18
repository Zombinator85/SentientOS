# Host Fulfillment Authorization Consumption Custody

This organ binds one explicit future-fulfillment request envelope to one exact current local authorization grant evidence chain. It recomputes the source reference from the issue receipt, local grant, grant verification, authorization ledger, ledger predecessor digest, expiry evaluation, and revocation receipts before any admission.

The runtime is metadata-only. It records whether the request fits the current grant evidence; it does not grant fulfillment, authorize an executor, request privileged-effect admission, invoke a backend, execute an effect, mutate the host, or prove an effect.

Freshness is evaluated against the injected current clock and request time. Stale historical `not_expired` expiry evidence, expired grants, backdated requests, request times beyond grant bounds, future expiry evaluations, and expiry evidence for another grant are denied before admission and before ledger append.

Successful consumption requires `FULFILLMENT_AUTHORIZATION_CONSUMPTION` admission and writes one idempotent append-only ledger entry. Exact replay returns the prior receipt without duplicate append; reused idempotency keys or request identities with different bytes are conflicts.

World-State and dashboard projections are read-only lifecycle evidence: request, source, plan, admission, verification, assessment, receipt or denial, ledger entry, and ledger. They are never execution, fulfillment, backend, host-mutation, or effect proof.
