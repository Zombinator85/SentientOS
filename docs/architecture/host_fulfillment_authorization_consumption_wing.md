# Host Fulfillment Authorization Consumption Wing

This wing follows the [Host Local Authorization Grant Wing](host_local_authorization_grant_wing.md). A local authorization grant is authority metadata, not fulfillment. Fulfillment authorization consumption checks whether a future fulfillment request fits a local authorization grant before any future executor is allowed to proceed.

## Boundary

Fulfillment authorization consumption is not fulfillment. Scope match is not execution. Grant verification is not host mutation. A consumption receipt does not execute. A denial receipt does not execute.

This wing does not execute host actions, fulfill host actions, mutate host state, write fan/PWM controls, perform thermal actuation, mutate power profiles, kill processes, restart services, install packages or drivers, clean up or delete files, perform network egress, invoke providers, assemble/export prompts, transport federation state, or perform remote execution.

`authorization_consumed_for_future_fulfillment=true` may appear only on a verified, scope-matched, active-grant consumption receipt. Even then, `fulfillment_granted=false`, `effect_performed=false`, `host_mutation_performed=false`, and all concrete action flags remain false.

## Records

- **FulfillmentAuthorizationRequest:** metadata-only request record for a future fulfillment executor's requested domain, backend class, scope labels, time label, required labels, blocked actions, warnings, risks, and digest.
- **GrantConsumptionVerification:** metadata-only verification that copies local grant and local verification status into a consumption posture. It has `authorizes_fulfillment=false`.
- **FulfillmentScopeMatchAssessment:** metadata-only requested-scope versus granted-scope assessment. Scope match is not execution.
- **FulfillmentAuthorizationConsumptionReceipt:** metadata-only receipt that records authorization consumption posture for future fulfillment. The receipt does not execute and does not grant fulfillment.
- **FulfillmentAuthorizationDenialReceipt:** metadata-only denial receipt for blocked, incomplete, contradicted, expired, revoked, or out-of-scope consumption attempts. The denial receipt does not execute.

## Future fulfillment remains deferred

Real fulfillment remains deferred. Real actuation remains deferred. Future cooling, power, service, and cleanup actions remain behind a future fulfillment executor plus control-plane admission, audit receipt, rollback receipt, effect receipt, postcondition checks, runtime supervisor observation, immutable trace, and safety gates.

Future cooling consumption preserves fan/PWM and thermal blocked action labels. Future power consumption preserves power mutation blocked action labels. Future cleanup consumption preserves cleanup/delete blocked action labels. Future service consumption preserves service restart/process kill blocked action labels.

The authority ladder remains:

observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → live-grant readiness → local authorization grant → fulfillment authorization consumption → fulfill → effect receipt → postcondition check → audit → rollback.

This wing covers **fulfillment authorization consumption/pre-fulfillment only**.

## Reviewer proof bundle integration

The reviewer proof bundle includes `fulfillment_authorization.json`. The artifact is reviewer proof only and metadata only. It demonstrates a safe sample where a local authorization grant is active, local grant verification is valid, fulfillment authorization consumption may be recorded, but `fulfillment_granted=false`, `effect_performed=false`, `host_mutation_performed=false`, and real actuation remains deferred.

## Implementation links

- Module: `sentientos/fulfillment_authorization.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_fulfillment_authorization.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, `tests/test_capability_registry.py`, `tests/test_reviewer_release_readiness_index.py`

Next wing: [Host Fulfillment Executor Contract Wing](host_fulfillment_executor_contract_wing.md). Executor contract is not an executor; backend declaration does not load/invoke backend; dry-run plan is not dry-run execution; admission packet is not control-plane admission; real actuation remains deferred.

Proof path: `docs/architecture/host_fulfillment_executor_contract_wing.md`.
