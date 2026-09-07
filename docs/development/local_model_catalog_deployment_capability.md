# Production local-model catalog deployment capability

`sentientos.local_model_catalog.deploy` has a deterministic controller implementation,
but its registry definition is not a grant, lease, live deployment, or successful state transition. Catalog
deployment is privileged because it changes which validated metadata production
selection and acquisition may treat as authoritative. A valid candidate and a
successful sovereign publication establish evidence and eligibility, not authority.

Only an explicitly operator-authorized
`deterministic_catalog_deployment_controller` may hold a future grant. Stochastic
or commissioned models, maintenance implementation workers, model curators, and
the `deterministic_publication_controller` are ineligible and cannot inherit or
self-grant it. Publication capability, publication success, receipt possession,
and bootstrap eligibility never mint a deployment grant.

The definition admits exactly four effects:

1. `exact_verified_publication_receipt_read`;
2. `exact_deployment_eligible_catalog_candidate_read`;
3. `authoritative_catalog_compare_and_swap`; and
4. `catalog_deployment_receipt_write`.

The controller validates the catalog schema and semantic digest, model ID,
artifact SHA-256 and byte size, canonical sovereign URL, immutable upstream
revision, and execution routes. It must independently validate the publication
receipt semantic digest, `object_verified = true`, complete streamed remote SHA-256,
remote digest and size, final publication status, and an exact receipt-to-candidate
match. That evidence is necessary but remains distinct from the explicit deployment
grant or lease.

The canonical installation-scoped custody, locking, complete multi-model evidence,
receipt, and recoverable transaction law is defined by
[`local_model_catalog_deployment_architecture.md`](local_model_catalog_deployment_architecture.md)
and its machine-readable projection. The custody transition is a deterministic compare-and-swap. Genesis requires an
explicit expected-absent state. Every replacement requires the exact observed
previous catalog semantic digest and the exact proposed digest. Mutation may occur
only when expected and observed state match; stale proposals and blind overwrite
fail closed. The future controller must atomically publish only the canonical
authoritative catalog custody object and durably write one bounded transition
receipt. `sentientos.local_model_catalog_deployment` implements the fixed installation-
scoped CAS, immutable intent/stage/receipt/finalization records, and deterministic
recovery classifier. It only consumes externally supplied, exactly bound authority;
the repository has no production issuer and no real catalog has been deployed.

The capability excludes curation, artifact identity changes, model-mirror contact,
provider or credential access, arbitrary destinations, mutable aliases, Hugging
Face substitution, model-byte acquisition, commissioning, activation, inference,
arbitrary runtime routes or configuration, Git publication, software deployment,
shell access, generic filesystem mutation, and authority expansion. The existing
curator-side create-only catalog publisher remains candidate publication, not this
updateable authoritative-custody transition. Consumers that accept a caller-supplied
catalog path currently bind its semantic digest but do not prove deployed custody;
that proof must be added only by the future controller/consumer integration task.
