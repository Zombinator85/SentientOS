# Host Embodiment Substrate Phase 5: Actuation Fulfillment Scaffold

Phase 5 adds the Actuation Fulfillment Layer scaffold for host embodiment. It is
a dry-run / rehearsal-only organ that consumes Phase 4 Privilege Broker review
receipts and produces deterministic fulfillment rehearsal plans and fulfillment
rehearsal receipts.

Phase 5 is not real actuation. Fulfillment rehearsal is not real fulfillment. A
rehearsal receipt is not an effect receipt. No host mutation occurs.

## Authority ladder

The authority ladder remains:

`observe → model → propose → broker eligibility → rehearse → authorize → fulfill → audit → rollback`

Phase 5 covers only `rehearse`. It does not authorize, fulfill, audit effects,
or execute rollback.

## What Phase 5 creates

`sentientos/actuation_fulfillment.py` defines metadata-only records:

1. `ActuationFulfillmentPolicy` — the default rehearsal policy, required future
   gates, and blocked action vocabulary.
2. `ActuationFulfillmentPlan` — a dry-run plan derived from a broker review
   receipt.
3. `ActuationFulfillmentRehearsalReceipt` — a deterministic receipt that records
   the rehearsal classification.
4. `ActuationFulfillmentValidationResult` — validation findings for plans and
   rehearsal receipts.

The non-mutating pipeline is now:

`collector results → telemetry snapshot → pressure report → policy decision → proposal receipt → privilege broker eligibility decision → privilege broker review receipt → fulfillment rehearsal plan → fulfillment rehearsal receipt`

Every stage remains metadata-only and non-mutating.

## Fulfillment rehearsal is not real fulfillment

Phase 5 may classify how a future action would need to be fulfilled, but it does
not perform that future action. It does not call control-plane execution, does
not admit a privileged host effect, and does not create an effect receipt.

The plan preserves explicit non-effect flags including:

- `metadata_only=True`
- `rehearsal_only=True`
- `authorization_granted=False`
- `fulfillment_granted=False`
- `host_mutation_performed=False`
- `fan_pwm_write_performed=False`
- `thermal_actuation_performed=False`
- `power_profile_mutation_performed=False`
- `process_kill_performed=False`
- `service_restart_performed=False`
- `package_install_performed=False`
- `driver_install_performed=False`
- `file_cleanup_performed=False`
- `provider_invocation_performed=False`
- `network_performed=False`
- `prompt_assembly_performed=False`

## Rehearsal receipt is not an effect receipt

A `ActuationFulfillmentRehearsalReceipt` records only dry-run rehearsal evidence.
It is not an effect receipt and cannot be used as proof of host mutation.

The rehearsal receipt preserves explicit non-effect flags:

- `rehearsal_only=True`
- `dry_run_only=True`
- `does_not_execute=True`
- `does_not_mutate_host=True`
- `does_not_authorize_fulfillment=True`
- `effect_not_performed=True`
- `requires_control_plane_admission_for_future_action=True`
- `requires_operator_or_policy_approval_for_future_action=True`
- `requires_audit_receipt_for_future_action=True`
- `requires_rollback_receipt_for_future_action=True`
- `requires_effect_receipt_for_future_action=True`
- `requires_postcondition_check_for_future_action=True`

## Domains, backend classes, and gates

Phase 5 prepares a future real Actuation Fulfillment Layer by defining domains,
backend classes, required gates, rehearsal steps, expected postconditions, and
rollback requirements. Those definitions are still rehearsal metadata only.

| Broker privilege domain | Fulfillment rehearsal domain | Backend class | Non-effect posture |
| --- | --- | --- | --- |
| `diagnostics_only` | `diagnostics_only` | `no_backend_required` | Diagnostics metadata only. |
| `operator_review` | `operator_review` | `operator_manual_backend_future` | Operator review metadata only. |
| `resource_pressure_review` | `resource_pressure_review` | `diagnostic_backend_future` | Rehearses diagnostics/review only. |
| `thermal_safety_review` | `thermal_safety_review` | `diagnostic_backend_future` | Thermal safety review only; no thermal actuation. |
| `disk_safety_review` | `disk_safety_review` | `diagnostic_backend_future` | Disk safety review only; no cleanup/deletion. |
| `service_health_review` | `service_health_review` | `service_backend_future` | Service health review only; no restart. |
| `future_cooling_policy_review` | `future_cooling_rehearsal` | `cooling_backend_future` | Future cooling rehearsal only; fan/PWM and thermal actions remain blocked. |
| `future_power_policy_review` | `future_power_rehearsal` | `power_backend_future` | Future power rehearsal only; power profile mutation remains blocked. |
| `future_cleanup_policy_review` | `future_cleanup_rehearsal` | `cleanup_backend_future` | Future cleanup rehearsal only; cleanup/deletion remains blocked. |

Future real fulfillment still requires control-plane admission,
operator/policy approval, audit receipt, rollback receipt, panic stop where
applicable, hardware allowlist where applicable, OS backend declaration,
bounds/cooldown policy where applicable, rehearsal, dry-run evidence, effect
receipt, and postcondition check.

## Blocked/deferred action classes

The following remain blocked/deferred in Phase 5:

- No direct fan/PWM control occurs.
- No thermal actuation occurs.
- No power profile mutation occurs.
- No process killing occurs.
- No service restart occurs.
- No package installation occurs.
- No driver installation occurs.
- No cleanup/deletion occurs.
- No network egress occurs.
- No provider invocation occurs.
- No prompt assembly or prompt export occurs.
- No federation transport/sync/adoption occurs.
- No remote execution occurs.

## Broker eligibility is still not authorization

Privilege Broker eligibility is not authorization. A broker review receipt is not
fulfillment. Phase 5 can only rehearse fulfillment planning after broker review;
it cannot convert eligibility into authority.

Eligible broker receipts may produce rehearsal-ready diagnostics/operator-review
plans. Eligible-with-conditions broker receipts may produce
rehearsal-ready-with-conditions plans only when condition gates are preserved.
Blocked, incomplete, or contradicted broker receipts produce blocked,
incomplete, or contradicted fulfillment plans.

Any source broker receipt that claims authorization, fulfillment, execution, or
host mutation is treated as contradicted by the Phase 5 scaffold.

## Proof command

```bash
python -m scripts.run_tests -q tests/test_actuation_fulfillment.py tests/test_privilege_broker.py tests/test_capability_registry.py
```

## Related docs

- `docs/architecture/host_embodiment_substrate_phase1.md`
- `docs/architecture/host_embodiment_substrate_phase2_read_only_discovery.md`
- `docs/architecture/host_embodiment_substrate_phase3_policy_receipts.md`
- `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md`
- `docs/architecture/sentientos_trajectory_and_missing_organs.md`
- `docs/architecture/public_technical_overview.md`
- `docs/architecture/reviewer_release_readiness_index.md`


## Host Embodiment Execution Proof Wing

Next proof/readiness wing: `docs/architecture/host_embodiment_execution_proof_wing.md`. Execution readiness is not authorization; the future effect receipt schema is not proof of effect; the Runtime Supervisor does not restart/kill services; real actuation remains deferred.

## Next wing: Authorization Review

After the Execution Proof Wing, see `docs/architecture/host_embodiment_authorization_review_wing.md`. Authorization review is not authorization; a future authorization grant schema is not a real grant; real fulfillment and real actuation remain deferred.

## Controlled authorization and trace link

Fulfillment rehearsal remains non-mutating. The [Host Embodiment Controlled Authorization + Trace Wing](host_embodiment_controlled_authorization_and_trace_wing.md) links this scaffold into a reviewer trace while keeping real fulfillment, host mutation, fan/PWM writes, thermal actuation, service restart, power mutation, and cleanup/delete deferred or blocked.

Proof path: docs/architecture/host_embodiment_controlled_authorization_and_trace_wing.md
