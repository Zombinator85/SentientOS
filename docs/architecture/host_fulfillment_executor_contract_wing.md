# Host Fulfillment Executor Contract Wing

This wing follows the [Host Fulfillment Authorization Consumption Wing](host_fulfillment_authorization_consumption_wing.md). Consuming authorization is not fulfillment, and this executor contract layer is not an executor. It records the metadata a future host fulfillment executor would need to prove before any real execution backend could exist.

## Boundary

The executor contract is not an executor. An executor backend declaration does not load or invoke backend code. An executor dry-run plan is not dry-run execution. An executor admission packet is not control-plane admission. An executor contract readiness receipt does not implement an executor, grant fulfillment, perform effects, or mutate host state.

This wing does not execute host actions, fulfill host actions, mutate host state, write fan/PWM controls, perform thermal actuation, mutate power profiles, kill processes, restart services, install packages or drivers, clean up or delete files, perform network egress, invoke providers, assemble/export prompts, transport federation state, perform remote execution, or expand runtime authority.

## Records

- **FulfillmentExecutorContract:** metadata-only contract for the requested fulfillment domain, future backend class, executor domain, required executor labels, blocked actions, warnings, risks, and digest. It is `contract_only=true`, `executor_implemented=false`, `backend_loaded=false`, `fulfillment_granted=false`, `effect_performed=false`, and `host_mutation_performed=false`.
- **ExecutorBackendDeclaration:** declaration-only metadata for a future backend class and supported executor domains. Backend declaration does not load or invoke backend code; `backend_loaded=false` and `backend_invoked=false` remain invariant.
- **ExecutorPreconditionManifest:** metadata-only list of prerequisite labels and missing labels for a future executor. It is not enforcement and performs no effect.
- **ExecutorDryRunPlan:** plan-only metadata describing what a future dry-run would need to demonstrate. A dry-run plan is not a dry run execution; `dry_run_executed=false` remains invariant.
- **ExecutorAdmissionPacket:** packet-only metadata that names future control-plane, audit, effect receipt, postcondition, and rollback requirements. An admission packet is not control-plane admission; `control_plane_admission_granted=false` remains invariant.
- **ExecutorContractReadinessReceipt:** readiness-only metadata summarizing contract evidence. It does not implement an executor, load a backend, execute a dry run, grant control-plane admission, grant fulfillment, perform effects, mutate host state, write fan/PWM controls, perform thermal/power/service/cleanup actions, invoke providers, open network egress, or assemble prompts.

## Future fulfillment remains deferred

Real fulfillment remains deferred. Real actuation remains deferred. Future cooling, power, service, and cleanup actions remain behind future executor implementation, control-plane admission, audit, effect receipt, postcondition checks, rollback, supervisor observation, immutable trace, panic stop, and safety gates.

Future cooling executor contracts preserve fan/PWM and thermal blocked action labels. Future power executor contracts preserve power mutation blocked action labels. Future cleanup executor contracts preserve cleanup/delete blocked action labels. Future service executor contracts preserve service restart/process kill blocked action labels.

The authority ladder remains:

observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → live-grant readiness → local authorization grant → fulfillment authorization consumption → executor contract → fulfill → effect receipt → postcondition check → audit → rollback.

This wing covers **executor contract/readiness only**.

## Reviewer proof bundle integration

The reviewer proof bundle includes `executor_contract.json`. The artifact is reviewer proof only and metadata only. It demonstrates a safe sample where authorization has been consumed for future fulfillment and executor contract records are built, while `executor_implemented=false`, `backend_loaded=false`, `backend_invoked=false`, `dry_run_executed=false`, `control_plane_admission_granted=false`, `fulfillment_granted=false`, `effect_performed=false`, and `host_mutation_performed=false`.

## Implementation links

- Module: `sentientos/fulfillment_executor_contract.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_fulfillment_executor_contract.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, `tests/test_capability_registry.py`, `tests/test_reviewer_release_readiness_index.py`


See also: [Host Dry-Run Execution Harness Wing](host_dry_run_execution_harness_wing.md) (`docs/architecture/host_dry_run_execution_harness_wing.md`), which is simulation-only; dry-run execution is not real fulfillment, dry-run result is not an effect receipt, dry-run receipt is not proof of host mutation, and real actuation remains deferred.

See also: [Host Dry-Run Effect Verification / Audit Closure Wing](host_dry_run_audit_closure_wing.md), which follows the dry-run execution harness and remains metadata-only; it does not create real effect receipts, real postcondition checks, real rollback, production audit receipts, or actuation.

Proof path: docs/architecture/host_dry_run_audit_closure_wing.md
