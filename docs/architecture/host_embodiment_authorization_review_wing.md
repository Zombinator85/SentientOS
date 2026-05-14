# Host Embodiment Authorization Review Wing

The Host Embodiment Authorization Review Wing follows the Host Embodiment
Execution Proof Wing. The Execution Proof Wing produces an
`ExecutionReadinessManifest`; this wing asks only whether that readiness manifest
is complete enough, safe enough, and bounded enough to be presented for future
operator/policy authorization consideration.

This wing is metadata-only authorization review. It is not authorization, not a
real authorization grant, not real actuation, not execution, not host mutation,
not direct fan/PWM control, not thermal actuation, not power profile mutation,
not process killing, not service restart, not package or driver installation,
not file cleanup or deletion, not network egress, not provider invocation, not
prompt assembly/export, not federation transport/sync/adoption, and not remote
execution.

## Authority ladder

The authority ladder remains:

`observe → model → propose → broker eligibility → rehearse → readiness → authorization review → authorize → fulfill → effect receipt → postcondition check → audit → rollback`

This wing covers `authorization review` only. It does not authorize, fulfill,
create an effect receipt from a real effect, perform a postcondition check from a
real effect, audit a real effect, or execute rollback.

## Core boundaries

- Execution readiness is not authorization.
- A future effect schema is not proof of effect.
- A postcondition plan is not a postcondition check from a real effect.
- A rollback plan is not rollback execution.
- A runtime supervisor report is not permission to restart/kill.
- An authorization review decision is not an authorization grant; authorization review is not authorization grant.
- An authorization review receipt is not fulfillment.
- A Future Authorization Grant schema is not a real grant.
- Real fulfillment remains deferred.
- Real actuation remains deferred.

## Review artifacts

`sentientos/authorization_review.py` defines the authorization-review artifacts:

1. `AuthorizationReviewPacket` records the source execution readiness manifest,
   source digest, proof identifiers, readiness status, authorization-review
   gates, satisfied/missing gates, blocked actions, warnings, and risk codes.
   It is `metadata_only`, `review_only`, and never grants authorization or
   fulfillment.
2. `AuthorizationReviewDecision` records the authorization domain, approval
   class, decision status, required/missing gates, blocked actions, warnings, and
   risks. It explicitly keeps authorization, fulfillment, effect, host mutation,
   fan/PWM, thermal, power, service restart, cleanup, provider, network, and
   prompt flags false.
3. `AuthorizationReviewReceipt` records that review happened. It is a receipt of
   review only: authorization is not granted, fulfillment is not authorized, no
   host mutation occurs, and future action still requires control-plane
   admission, operator/policy approval, audit receipt, rollback receipt, effect
   receipt, and postcondition check.
4. `FutureAuthorizationGrantSchema` is a placeholder schema for a possible
   future grant record. It is `schema_only`, `future_use_only`, not an
   authorization grant, does not execute, does not mutate host state, and does
   not authorize fulfillment.

## Domain mapping and gates

| Execution readiness effect domain | Authorization review domain | Approval class | Extra gates/blockers |
| --- | --- | --- | --- |
| `diagnostics_only` | `diagnostics_authorization_review` | `no_operator_action_required_for_diagnostics` | Review-only diagnostics; no action grant. |
| `operator_review` | `operator_review_authorization_review` | `operator_explicit_approval_required` | Operator review only; no fulfillment grant. |
| `resource_pressure_review` | `resource_pressure_authorization_review` | `operator_explicit_approval_required` | Control-plane, approval, audit, rollback, effect receipt, postcondition, immutable trace remain required. |
| `thermal_safety_review` | `thermal_safety_authorization_review` | `policy_explicit_approval_required` | Runtime supervisor observation remains required; cooling actuation is not authorized. |
| `disk_safety_review` | `disk_safety_authorization_review` | `policy_explicit_approval_required` | Dry-run/rehearsal evidence remains required; cleanup/deletion is not authorized. |
| `service_health_review` | `service_health_authorization_review` | `operator_explicit_approval_required` | Runtime supervisor observation remains required; restart/kill remains blocked. |
| `future_cooling_effect` | `future_cooling_authorization_review` | `future_hardware_safety_approval_required` | Hardware allowlist, OS backend, bounds, cooldown, panic stop, control-plane admission, audit, rollback, effect receipt, postcondition check, immutable trace; fan/PWM and thermal actuation remain blocked. |
| `future_power_effect` | `future_power_authorization_review` | `dual_operator_policy_approval_required` | OS backend, bounds/policy, control-plane admission, audit, rollback, effect receipt, postcondition check, immutable trace; power mutation remains blocked. |
| `future_cleanup_effect` | `future_cleanup_authorization_review` | `future_filesystem_scope_approval_required` | Filesystem scope, path/scope labels, dry-run/rehearsal evidence, control-plane admission, audit, rollback, effect receipt, postcondition check; cleanup/delete remain blocked. |
| `future_service_effect` | `future_service_authorization_review` | `future_service_scope_approval_required` | Service scope, runtime supervisor observation, control-plane admission, audit, rollback, effect receipt, postcondition check; service restart/process kill remain blocked. |

## Pipeline position

The non-mutating pipeline is now:

`collector results → telemetry snapshot → pressure report → policy decision → proposal receipt → broker eligibility decision → broker review receipt → fulfillment rehearsal plan → fulfillment rehearsal receipt → effect receipt contract → future effect receipt schema → postcondition plan → rollback plan → execution readiness manifest → authorization review packet → authorization review decision → authorization review receipt → future authorization grant schema`

All stages remain metadata-only and non-mutating. Readiness and review do not
collapse into authorization. Future cooling, power, service, and cleanup actions
remain behind explicit future authorization, control-plane admission, audit,
rollback, effect receipt, and postcondition checks.

## Reviewer proof links

- Module: `sentientos/authorization_review.py`
- Upstream proof module: `sentientos/effect_proof.py`
- Capability registry: `sentientos/capability_registry.py`
- Authorization review tests: `tests/test_authorization_review.py`
- Registry tests: `tests/test_capability_registry.py`
- Docs regression: `tests/test_reviewer_release_readiness_index.py`

## Next wing

The next non-mutating organ is the [Host Embodiment Controlled Authorization + Trace Wing](host_embodiment_controlled_authorization_and_trace_wing.md). It defines a controlled grant contract, schema-only/future-use-only grant and revocation records, a metadata-only ledger, and a reviewer demo trace. It does not grant live authorization or perform effects.

Proof path: docs/architecture/host_embodiment_controlled_authorization_and_trace_wing.md
