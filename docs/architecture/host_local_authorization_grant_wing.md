# Host Local Authorization Grant Wing

This wing follows the [Host Live-Grant Readiness Wing](host_live_grant_readiness_wing.md). Live-grant readiness is not a live grant; it is a preflight posture. The local authorization grant wing creates bounded local authorization grant records only after readiness prerequisites and operator/policy approval evidence are present.

## Boundary

A local authorization grant is authority metadata, not fulfillment. A local authorization grant does not execute. A local authorization grant does not mutate host state. It does not write fan/PWM controls, perform thermal actuation, mutate power profiles, kill processes, restart services, install packages or drivers, clean up or delete files, perform network egress, invoke providers, assemble/export prompts, transport federation state, or perform remote execution.

An active local authorization grant may record `live_authorization_granted=true`, but that flag remains record-local authority metadata. It does not set `fulfillment_granted`, does not perform an effect, and does not bypass future fulfillment checks.

## Records

- **OperatorApprovalEvidence:** metadata-only operator approval evidence with scope, time bounds, expiry, revocation, risk, warning, and digest labels.
- **PolicyApprovalEvidence:** metadata-only policy approval evidence with scope, time bounds, expiry, revocation, risk, warning, and digest labels.
- **LocalAuthorizationGrant:** a scoped, expiring, revocable local authority record. It is not fulfillment and has all effect and host-mutation flags false.
- **LocalAuthorizationGrantLedger:** metadata-only aggregation of grant, revocation, and expiry posture.
- **LocalAuthorizationGrantRevocationReceipt:** revocation metadata. The revocation receipt records revocation metadata and does not execute host action.
- **LocalAuthorizationGrantExpiryEvaluation:** expiry metadata. Expiry evaluation is metadata-only and evaluates labels/timestamps only.
- **LocalAuthorizationGrantVerification:** lookup/check metadata. Grant verification is not fulfillment authorization and has `authorizes_fulfillment=false`.

## Grant conditions

A grant can be active only when live-grant readiness/preflight is ready or ready-with-conditions and operator approval evidence plus policy approval evidence are present. Blocked, incomplete, or contradicted preflight/evidence produces blocked, incomplete, or contradicted grant records.

Future cooling, power, service, and cleanup grants preserve blocked action labels. Future cooling keeps fan/PWM and thermal action labels blocked. Future power keeps power mutation blocked. Future service keeps service restart and process kill blocked. Future cleanup keeps cleanup and delete labels blocked.

## Future fulfillment remains deferred

Real fulfillment remains deferred. Real actuation remains deferred. Future cooling/power/service/cleanup actions remain behind future fulfillment verification, control-plane admission, audit, rollback, effect receipt, postcondition checks, runtime supervisor observation, immutable trace, and safety gates.

The authority ladder remains:

observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → live-grant readiness → local authorization grant → fulfill → effect receipt → postcondition check → audit → rollback.

This wing covers **local authorization grant lifecycle only**.

## Reviewer proof bundle integration

The reviewer proof bundle includes `local_authorization.json`. That artifact is reviewer proof only and metadata only. It includes deterministic sample operator and policy evidence, a bounded local authorization grant record, expiry evaluation, verification, revocation schema example, and ledger summary. The sample may show an active local authorization record, but `fulfillment_granted=false`, `effect_performed=false`, `host_mutation_performed=false`, and grant verification does not authorize fulfillment.

## Implementation links

- Module: `sentientos/local_authorization_grant.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_local_authorization_grant.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, `tests/test_capability_registry.py`, `tests/test_reviewer_release_readiness_index.py`
