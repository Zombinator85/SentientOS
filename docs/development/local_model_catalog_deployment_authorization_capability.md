# Catalog deployment authorization issuance capability

`sentientos.local_model_catalog.deployment_authorization.issue` now has a bounded,
model-distribution runtime implementation for
`deterministic_catalog_deployment_authorization_controller`. This principal is separate
from `deterministic_catalog_deployment_controller`, which consumes externally supplied
authority and cannot mint, widen, renew, or self-grant it. This admission contract is
blessed under the repository's operator-accountability and least-privilege procedure
law preserved in `docs/AGENTS_DOCTRINE_ARCHIVE.md`; it changes definition eligibility,
not live privilege.

The exact future issuance effects are:

1. `exact_operator_approval_evidence_read`;
2. `exact_verified_publication_receipt_read`;
3. `exact_deployment_eligible_catalog_candidate_read`;
4. `bounded_catalog_deployment_grant_issue`;
5. `bounded_catalog_deployment_lease_issue`; and
6. `catalog_deployment_authorization_receipt_write`.

An implementation task must explicitly name `explicit operator approval`, `verified
publication`, and `exact prior-state`. Admission remains definition eligibility only:
`capability_granted` is false, and neither an admitted task nor this definition creates
operator approval, a grant, a lease, controller execution, or deployment evidence.

## Existing machinery and specialization boundary

The future issuer must reuse control-plane
`LOCAL_AUTHORIZATION_GRANT_ISSUANCE` admission and the generic operator/policy evidence,
bounded expiry, revocation verification, and ledger concepts in
`local_authorization_grant.py`. `controlled_authorization.py` remains schema- and
contract-only and is not live authority. Generic local-authorization domain/scope labels
do not prove catalog resources, so the future specialized issuer must independently and
exactly bind one transition: issuer and approval-evidence identities; target
`deterministic_catalog_deployment_controller`; target
`sentientos.local_model_catalog.deploy`; its exact four deployment effects; correlation,
installation, derived catalog-custody, candidate-catalog semantic digest, expected prior
authoritative state, and verified-publication-evidence identities; bounded validity; and
separate grant and lease identities. It must preserve canonical expiry, revocation,
panic, rollback, control-plane admission, and durable audit requirements.

No stochastic or commissioned model, maintenance worker, curator, publication or
deployment controller, acquisition fulfillment controller, or runtime activation
controller is eligible to hold issuance authority. Publication authority, publication
evidence, artifact possession, an approval packet, readiness receipt, active generic
local-authorization record, or capability definition cannot be promoted into it.

The runtime implementation consumes immutable external approval, independently validates
the complete catalog and the controller's shared deep publication-evidence contract,
obtains `LOCAL_AUTHORIZATION_GRANT_ISSUANCE` control-plane admission, and writes exact
grant, lease, and issuance-receipt records under the fixed installation-state path
`authorization/model-catalog-deployment/`. Grant lifetime is finite and at most 3600
seconds; a lease can only narrow it. Exact retries recover grant-only and grant-plus-lease
partial issuance and return replay only when all three expected objects are identical.

No genuine production approval or issuance event is performed by implementation tests.
Real authorization exercise and deployment, consumer custody enforcement, sovereign Qwen
publication, acquisition, commissioning, activation, inference, commissioned-local
maintenance E2E, and Windows durable-state support remain deferred. Issuance is not
catalog deployment.
