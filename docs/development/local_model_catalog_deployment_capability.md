# Production local-model catalog deployment capability

`sentientos.local_model_catalog.deploy` is an admitted **capability definition**,
not a grant, lease, controller, deployment, or successful state transition. Catalog
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

A future controller must validate the catalog schema and semantic digest, model ID,
artifact SHA-256 and byte size, canonical sovereign URL, immutable upstream
revision, and execution routes. It must independently validate the publication
receipt semantic digest, `object_verified = true`, complete streamed remote SHA-256,
remote digest and size, final publication status, and an exact receipt-to-candidate
match. That evidence is necessary but remains distinct from the explicit deployment
grant or lease.

The custody transition is a deterministic compare-and-swap. Genesis requires an
explicit expected-absent state. Every replacement requires the exact observed
previous catalog semantic digest and the exact proposed digest. Mutation may occur
only when expected and observed state match; stale proposals and blind overwrite
fail closed. The future controller must atomically publish only the canonical
authoritative catalog custody object and durably write one bounded transition
receipt. This repository currently has no such controller or receipt, so this
contract does not designate a live catalog path or mutate catalog state.

The capability excludes curation, artifact identity changes, model-mirror contact,
provider or credential access, arbitrary destinations, mutable aliases, Hugging
Face substitution, model-byte acquisition, commissioning, activation, inference,
arbitrary runtime routes or configuration, Git publication, software deployment,
shell access, generic filesystem mutation, and authority expansion. The existing
curator-side create-only catalog publisher remains candidate publication, not this
updateable authoritative-custody transition. Consumers that accept a caller-supplied
catalog path currently bind its semantic digest but do not prove deployed custody;
that proof must be added only by the future controller/consumer integration task.
