# Host Real Effect Capability Admission Wing

This wing follows the [Host Dry-Run Effect Verification / Audit Closure Wing](host_dry_run_audit_closure_wing.md). Dry-run audit closure verifies simulated evidence only; it does **not** automatically permit real effects. Real effect capability admission is metadata-only implementation planning posture, not implementation.

## Boundary

Real effect capability admission is not implementation. The admission decision does not authorize implementation or execution. The implementation plan scaffold does not start implementation. The block/deferral receipt does not mutate host state.

This wing does not implement a real backend, load a backend, invoke a backend, fulfill a host action, execute a real effect, create a real effect receipt, perform a real host postcondition check, execute rollback, create a production audit receipt, actuate hardware, write fan/PWM controls, perform thermal actuation, mutate power profiles, restart services, kill processes, clean or delete files, install packages or drivers, call the OS, perform network egress, invoke providers, assemble prompts, transport federation changes, execute remotely, spawn subprocess execution, run shell execution, or call control-plane admission/execution.

## Records

- **RealEffectCapabilityCandidate** records a dry-run closure-backed candidate and keeps `metadata_only=true`, `candidate_only=true`, `implementation_not_started=true`, `real_backend_implemented=false`, `real_fulfillment_performed=false`, `real_effect_performed=false`, and `host_mutation_performed=false`.
- **RealEffectCapabilityAdmissionDecision** classifies the candidate as eligible for implementation planning, eligible with conditions, blocked, incomplete, or contradicted. It keeps `authorizes_implementation=false` and `authorizes_execution=false`.
- **RealEffectImplementationPlanScaffold** names future design work only. It keeps `plan_scaffold_only=true`, `implementation_not_started=true`, `backend_loaded=false`, `backend_invoked=false`, `real_fulfillment_performed=false`, `real_effect_performed=false`, and `host_mutation_performed=false`.
- **RealEffectCapabilityBlockReceipt** records why a capability remains blocked/deferred and keeps `block_receipt_only=true`, `implementation_not_started=true`, `real_backend_implemented=false`, `real_fulfillment_performed=false`, and `host_mutation_performed=false`.
- **RealEffectAdmissionBundle** packages candidate, decision, and plan-or-block posture while keeping `authorizes_implementation=false`, `authorizes_execution=false`, and all real-action flags false.

## Domain posture

Lower-risk domains such as diagnostics, operator review, and resource pressure may become implementation-planning candidates. Conditional domains must still satisfy explicit planning, operator, and security review labels.

Cooling/hardware control remains blocked by default. Real fan/PWM, thermal, power, service, and cleanup actions remain blocked/deferred. Future cooling preserves `fan_pwm_write` and `thermal_actuation` blocked actions. Future power preserves `power_profile_mutation`. Future service preserves `service_restart` and `process_kill`. Future cleanup preserves `file_cleanup` and `file_delete`.

Real fulfillment remains deferred. Real effect receipts remain deferred. Real postcondition checks remain deferred. Real rollback remains deferred. Production audit remains deferred. Real actuation remains deferred.

## Authority ladder

observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → safety gates → live-grant readiness → local authorization grant → fulfillment authorization consumption → executor contract → dry-run execution harness → dry-run verification/audit closure → real effect capability admission → implement real backend → fulfill → effect receipt → postcondition check → audit → rollback.

This wing covers **real effect capability admission and implementation planning only**.

## Reviewer proof bundle integration

The reviewer proof bundle includes `real_effect_admission.json`. The artifact shows that a dry-run closure can be evaluated for future implementation planning while no implementation starts, no backend loads, no backend invokes, no real fulfillment occurs, no real effect occurs, and no host mutation occurs.

## Implementation links

- Module: `sentientos/real_effect_admission.py`
- Dry-run closure source: `sentientos/dry_run_audit_closure.py`
- Reviewer bundle integration: `sentientos/reviewer_proof_bundle.py`
- Capability registry integration: `sentientos/capability_registry.py`
- Tests: `tests/test_real_effect_admission.py`, `tests/test_reviewer_proof_bundle.py`, `tests/test_build_reviewer_proof_bundle_script.py`, `tests/test_capability_registry.py`, `tests/test_reviewer_release_readiness_index.py`

After admission, the first intentionally real low-risk effect is the [Host Local Diagnostic Effect Pilot Wing](host_local_diagnostic_effect_pilot_wing.md), limited to an explicit diagnostic artifact write only.
