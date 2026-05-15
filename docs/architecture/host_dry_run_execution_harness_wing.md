# Host Dry-Run Execution Harness Wing

This wing follows the [Host Fulfillment Executor Contract Wing](host_fulfillment_executor_contract_wing.md). The executor contract is not an executor; it is readiness metadata. The dry-run execution harness is the next organ-sized wing and is still simulation-only: it can run only inert, deterministic, in-process simulated backend mappings against executor contract readiness records.

## Boundary

Dry-run execution is not real fulfillment. A dry-run result is not an effect receipt. A dry-run receipt is not proof of host mutation. `dry_run_executed=true` means only the in-process simulation mapping ran.

The harness does not create real host executors, does not create OS backend implementations, does not call control-plane admission/execution, and does not mutate host state. It performs no subprocess execution, shell execution, network egress, provider invocation, prompt assembly/export, filesystem cleanup/deletion, service-manager operation, process kill, hardware control, thermal write, power-profile mutation, or fan/PWM write.

## Records

- **DryRunExecutionHarnessPolicy:** metadata-only policy declaring supported dry-run domains, simulated backend classes, blocked action labels, and simulation-only status.
- **SimulatedBackendRegistry:** metadata-only registry of inert simulated backends. It is `simulated_only=true`, `no_real_backends=true`, and `host_mutation_performed=false`.
- **DryRunExecutionRequest:** request-only record tying an executor contract readiness receipt to a requested dry-run domain and simulated backend class. It has `does_not_execute_real_backend=true`.
- **DryRunExecutionResult:** simulation-only result. It may set `dry_run_executed=true`, but keeps `real_backend_invoked=false`, `real_fulfillment_performed=false`, `real_effect_performed=false`, `effect_performed=false`, and `host_mutation_performed=false`.
- **DryRunExecutionReceipt:** dry-run-receipt-only evidence that simulation ran. It is not real fulfillment, not an effect receipt, and not proof of host mutation.
- **DryRunExecutionBlockReceipt:** block/failure receipt for blocked, incomplete, contradicted, or unknown simulated-backend requests. It has `dry_run_executed=false`, `does_not_execute=true`, and `does_not_mutate_host=true`.

## Simulated backends

Simulated backends are pure deterministic mappings/functions inside `sentientos/dry_run_execution_harness.py`. They are labels and metadata, not real backend modules. Future cooling dry-runs preserve `fan_pwm_write` and `thermal_actuation` blocked actions. Future power dry-runs preserve `power_profile_mutation`. Future cleanup dry-runs preserve `file_cleanup` and `file_delete`. Future service dry-runs preserve `service_restart` and `process_kill`.

Any record that claims real backend invocation, real fulfillment, effect execution, host mutation, fan/PWM write, thermal actuation, power mutation, service restart, cleanup/delete, network, provider, prompt assembly, subprocess execution, shell execution, OS backend invocation, or control-plane admission execution is contradicted by validation.

## Future fulfillment remains deferred

Real fulfillment remains deferred. Real actuation remains deferred. Future cooling, power, service, and cleanup actions remain behind a future real executor implementation, control-plane admission, audit, effect receipt, postcondition checks, rollback, supervisor observation, immutable trace, panic stop, and safety gates.

The authority ladder remains:

observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → live-grant readiness → local authorization grant → fulfillment authorization consumption → executor contract → dry-run execution harness → fulfill → effect receipt → postcondition check → audit → rollback.

This wing covers **dry-run simulated execution only**.

## Reviewer proof bundle integration

The reviewer proof bundle includes `dry_run_execution.json`. The artifact is reviewer proof only and metadata only. It demonstrates a safe sample where executor contract readiness exists, the dry-run harness runs an inert simulated backend, `dry_run_executed=true` is allowed, and `real_backend_invoked=false`, `real_fulfillment_performed=false`, `real_effect_performed=false`, and `host_mutation_performed=false` remain invariant.

## Implementation links

- Module: `sentientos/dry_run_execution_harness.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_dry_run_execution_harness.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, `tests/test_capability_registry.py`, `tests/test_reviewer_release_readiness_index.py`

Next wing: [Host Dry-Run Effect Verification / Audit Closure Wing](host_dry_run_audit_closure_wing.md). It verifies dry-run evidence only; dry-run effect verification is not a real effect receipt, dry-run postcondition verification is not a real host postcondition check, dry-run rollback rehearsal is not real rollback, and dry-run audit closure is not a production audit receipt.

Proof path: docs/architecture/host_dry_run_audit_closure_wing.md
