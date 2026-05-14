# Host Embodiment Substrate Phase 4: Privilege Broker Eligibility Layer

Phase 4 adds the Privilege Broker eligibility layer for host embodiment. It
consumes Phase 3 host-resource proposal receipts and classifies whether each
receipt is eligible, conditionally eligible, blocked, incomplete, or
contradicted for future privileged-action consideration.

Phase 4 is not actuation. Eligibility is not authorization. A broker review
receipt is not fulfillment; broker review receipt is not fulfillment. The broker only records metadata about future gates
and missing prerequisites.

## Authority ladder

The host-embodiment ladder remains:

`observe → model → propose → broker eligibility → rehearse → authorize → fulfill → audit → rollback`

Phase 4 covers only `broker eligibility`. It does not skip to rehearsal,
authorization, fulfillment, audit, or rollback.

## What Phase 4 evaluates

`sentientos/privilege_broker.py` evaluates proposal receipts from
`sentientos/host_resource_policy.py` and produces two metadata-only artifacts:

1. `PrivilegeBrokerEligibilityDecision` — the broker classification for a source
   proposal receipt.
2. `PrivilegeBrokerReviewReceipt` — a deterministic review receipt recording the
   broker classification and future gates.

The intended non-mutating pipeline is:

`collector results → telemetry snapshot → pressure report → policy decision → proposal receipt → privilege broker eligibility decision → privilege broker review receipt`

Each broker decision records the source proposal kind, source receipt digest,
proposal status, proposal scope, pressure labels, privilege domain, eligibility
status, reason/warning/risk codes, required future gates, blocked actions, and
missing prerequisites.

## Eligibility is not authorization

A `privilege_broker_eligible_for_future_review` or
`privilege_broker_eligible_with_conditions` decision means only that a later
privileged-action request could be considered after all required gates are
present. It does not authorize host action and does not grant fulfillment.

Every eligibility decision preserves explicit non-effect flags:

- `metadata_only=True`
- `eligibility_only=True`
- `authorization_granted=False`
- `fulfillment_granted=False`
- `host_mutation_performed=False`
- `fan_pwm_write_performed=False`
- `thermal_actuation_performed=False`
- `process_kill_performed=False`
- `service_restart_performed=False`
- `package_install_performed=False`
- `driver_install_performed=False`
- `provider_invocation_performed=False`
- `network_performed=False`
- `prompt_assembly_performed=False`

## Broker receipt is not fulfillment

A `PrivilegeBrokerReviewReceipt` is a ledgerable review artifact only. It records
that review happened and which future gates remain required. It does not execute,
mutate, authorize fulfillment, or satisfy the future Actuation Fulfillment Layer.

Every broker receipt preserves explicit non-effect flags:

- `review_only=True`
- `eligibility_only=True`
- `does_not_execute=True`
- `does_not_mutate_host=True`
- `does_not_authorize_fulfillment=True`
- `requires_control_plane_admission_for_future_action=True`
- `requires_operator_or_policy_approval_for_future_action=True`
- `requires_audit_receipt_for_future_action=True`
- `requires_rollback_receipt_for_future_action=True`
- `requires_actuation_fulfillment_layer_for_future_action=True`

## Proposal kind mapping

| Proposal kind | Privilege domain | Broker posture |
| --- | --- | --- |
| `inspect_cpu_pressure_candidate` | `resource_pressure_review` | Eligible for future review when source receipt is valid and non-effect. |
| `inspect_memory_pressure_candidate` | `resource_pressure_review` | Eligible for future review when source receipt is valid and non-effect. |
| `inspect_disk_pressure_candidate` | `disk_safety_review` | Eligible for future review when source receipt is valid and non-effect. |
| `inspect_thermal_state_candidate` | `thermal_safety_review` | Eligible for future review only; no cooling authority. |
| `inspect_service_health_candidate` | `service_health_review` | Eligible for review only; service restart remains blocked/deferred. |
| `future_cooling_policy_candidate` | `future_cooling_policy_review` | Blocked if the Phase 3 receipt is blocked; otherwise eligible only with conditions. Never direct fulfillment. |
| `future_power_policy_candidate` | `future_power_policy_review` | Eligible only with conditions; no power-profile mutation. |
| `future_cleanup_policy_candidate` | `future_cleanup_policy_review` | Blocked if the Phase 3 receipt is blocked; otherwise eligible only with conditions. No cleanup mutation. |
| `request_operator_review_candidate` | `operator_review` | Eligible for operator review when source receipt is valid and non-effect. |
| `reduce_model_load_candidate` / `defer_heavy_task_candidate` | `resource_pressure_review` | Review/rehearsal candidate only; no fulfillment is granted. |

## Future gates by privileged class

Future cooling policy candidates require all of the following before any later
action could even be considered: hardware allowlist, OS backend declaration,
bounds policy, cooldown policy, panic stop, control-plane admission,
operator/policy approval, audit receipt, rollback receipt, rehearsal, and the
future Actuation Fulfillment Layer.

Future power policy candidates require OS backend declaration, bounds policy,
operator/policy approval, control-plane admission, audit receipt, rollback
receipt, rehearsal, and the future Actuation Fulfillment Layer.

Future cleanup policy candidates require dry-run/rehearsal, file/path scope
declaration, operator/policy approval, audit receipt, rollback receipt, and the
future Actuation Fulfillment Layer.

Service health review candidates keep `service_restart` in blocked actions.
Thermal and fan/PWM observations keep `fan_pwm_write` and `thermal_actuation` in
blocked actions when cooling is discussed.

## Explicitly forbidden in Phase 4

The Privilege Broker cannot:

- mutate host state;
- write fan/PWM controls;
- perform thermal actuation;
- change power profiles;
- kill processes;
- restart services;
- install packages or drivers;
- perform network calls or remote execution;
- invoke providers;
- assemble or export prompts;
- transport, sync, adopt, merge, apply, install, or execute federation evidence.

direct fan/PWM/thermal control remains blocked/deferred. Future
cooling/power/cleanup/service actions remain blocked behind future gates. The
future Actuation Fulfillment Layer is still required before effects can occur.

## Contradiction and incompleteness rules

Source proposal receipts that are blocked, incomplete, or contradicted do not
become eligible. They remain broker-blocked, broker-incomplete, or
broker-contradicted.

Any source receipt that claims execution, host mutation, fulfillment
authorization, missing future gates, or missing blocked-action evidence is
rejected as blocked or contradicted by the broker. This preserves the core
principle: a proposal receipt is not an effect, a policy decision is not
authorization, and a privilege broker eligibility decision is not fulfillment.

## Proof commands

```bash
python -m scripts.run_tests -q tests/test_privilege_broker.py tests/test_host_resource_policy.py tests/test_capability_registry.py
python -m scripts.run_tests -q tests/test_reviewer_release_readiness_index.py
python scripts/build_docs.py --check-deps
python scripts/build_docs.py
python scripts/verify_context_hygiene_prompt_boundaries.py
```


## Next phase

Phase 5 actuation fulfillment rehearsal is documented in `docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md`. Fulfillment rehearsal is not real fulfillment, and a rehearsal receipt is not an effect receipt. Direct fan/PWM/thermal control remains blocked/deferred, and power, service, and cleanup actions remain behind future authorization, admission, audit, rollback, effect receipt, and postcondition gates.


## Host Embodiment Execution Proof Wing

Next proof/readiness wing: `docs/architecture/host_embodiment_execution_proof_wing.md`. Execution readiness is not authorization; the future effect receipt schema is not proof of effect; the Runtime Supervisor does not restart/kill services; real actuation remains deferred.
