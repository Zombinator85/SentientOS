# Host Embodiment Controlled Authorization + Trace Wing

The next organ after this contract/trace layer is the [Host Actuation Safety Gate Wing](host_actuation_safety_gate_wing.md) (`docs/architecture/host_actuation_safety_gate_wing.md`), which declares metadata-only prerequisites and still grants no live authorization.
This wing follows the [Authorization Review Wing](host_embodiment_authorization_review_wing.md). The practical first-run reviewer command path is the [Reviewer First-Run Proof Bundle](reviewer_first_run_proof_bundle.md) (`docs/architecture/reviewer_first_run_proof_bundle.md`). It defines the controlled authorization grant contract and a reviewer-facing end-to-end trace across the non-mutating host-embodiment ladder.

## Boundary

Authorization review is not authorization. A controlled authorization contract is not a live grant. A grant record is schema-only/future-use-only. A revocation record is schema-only/future-use-only. The authorization ledger is metadata-only and does not grant authority.

This wing is contract/ledger/trace proof only. It does not execute, fulfill, mutate host state, write fan/PWM controls, change thermal settings, mutate power profiles, kill processes, restart services, clean up or delete files, install packages or drivers, perform network egress, invoke providers, assemble or export prompts, transport federation state, or perform remote execution.

## Authority ladder

The ladder remains:

observe → model → propose → broker eligibility → rehearse → readiness → authorization review → controlled grant contract → authorize → fulfill → effect receipt → postcondition check → audit → rollback.

This wing covers only **controlled grant contract** and **trace**. The authorize, fulfill, effect receipt, postcondition check, audit, and rollback stages remain future controlled work unless represented as non-mutating schema/proof artifacts.

## Controlled authorization contract

`sentientos/controlled_authorization.py` defines:

- `ControlledAuthorizationGrantContract`: required future grant fields, scope, expiry, revocation, audit, control-plane, rollback, effect receipt, postcondition, supervisor, immutable trace, and panic-stop gates.
- `ControlledAuthorizationGrantRecord`: schema-only/future-use-only record. It is not a live authorization grant and does not authorize fulfillment.
- `ControlledAuthorizationRevocationRecord`: schema-only/future-use-only revocation path record. It does not perform live revocation.
- `ControlledAuthorizationLedger`: metadata-only ledger scaffold. It records schema grant/revocation records but does not grant authority.

Future cooling, power, service, and cleanup scopes stay blocked/deferred. Future cooling keeps fan/PWM writes and thermal actuation blocked. Future power keeps power profile mutation blocked. Future service keeps service restart and process kill blocked. Future cleanup keeps cleanup and delete actions blocked.

## End-to-end demo trace

`sentientos/host_embodiment_trace.py` builds a deterministic reviewer proof trace using supplied fake/sample telemetry by default. The demo includes a thermal + PWM scenario to prove that PWM presence is telemetry, not authority.

The trace spans collector results, inventory, telemetry, pressure, policy, proposal receipts, broker eligibility/review, fulfillment rehearsal, execution proof, authorization review, future authorization schema, controlled authorization contract, schema-only grant record, schema-only revocation record, and metadata-only ledger.

Demo trace is reviewer proof only. The trace is demo/proof-only. It explicitly records no live authorization, no real fulfillment, no effect, no host mutation, no fan/PWM write, no thermal write, no power mutation, no service restart, no cleanup/delete, no provider invocation, no network egress, no prompt assembly/export, no federation transport, and no remote execution.

## Future live authority requirements

Future cooling/power/service/cleanup actions remain behind explicit future live authorization, control-plane admission, operator/policy identity, bounded scope, expiry, revocation path, audit receipt, rollback plan/receipt, effect receipt, postcondition checks, runtime supervisor observation, immutable trace, and panic-stop requirements.

Real fulfillment remains deferred. Real actuation remains deferred.

## Reviewer proof links

- Module: `sentientos/controlled_authorization.py`
- Trace builder: `sentientos/host_embodiment_trace.py`
- Tests: `tests/test_controlled_authorization.py`, `tests/test_host_embodiment_trace.py`
- Public proof map: [Reviewer Release Readiness Index](reviewer_release_readiness_index.md)

## Reviewer demo trace export

See [Host Embodiment Reviewer Demo Trace](host_embodiment_reviewer_demo_trace.md) for the deterministic JSON/Markdown export command. The export is reviewer proof only, uses fake/sample thermal+PWM telemetry by default, and preserves the proof that PWM presence is not control authority, the controlled authorization contract is not a live grant, grant/revocation records are schema-only/future-use-only, and real actuation remains deferred.

Proof path: docs/architecture/host_embodiment_reviewer_demo_trace.md

## Downstream readiness link

After controlled authorization contracts and safety gates, the [Host Live-Grant Readiness Wing](host_live_grant_readiness_wing.md) (`docs/architecture/host_live_grant_readiness_wing.md`) checks readiness/preflight metadata only. Controlled authorization contract is not a live grant, and live-grant readiness is not authorization.

Later ladder link: [Host Local Authorization Grant Wing](host_local_authorization_grant_wing.md) records scoped local authorization metadata after live-grant readiness without executing host actions.

Path link: `docs/architecture/host_local_authorization_grant_wing.md`.

See also the [Host Fulfillment Authorization Consumption Wing](host_fulfillment_authorization_consumption_wing.md), which sits after local authorization grants and before any future fulfillment executor. Consumption receipts do not execute.

Path: `docs/architecture/host_fulfillment_authorization_consumption_wing.md`.

Downstream proof links include [Host Fulfillment Authorization Consumption Wing](host_fulfillment_authorization_consumption_wing.md) and [Host Fulfillment Executor Contract Wing](host_fulfillment_executor_contract_wing.md); both preserve the boundary that records and contracts are not fulfillment or execution.

Proof path: `docs/architecture/host_fulfillment_executor_contract_wing.md`.


See also: [Host Dry-Run Execution Harness Wing](host_dry_run_execution_harness_wing.md) (`docs/architecture/host_dry_run_execution_harness_wing.md`), which is simulation-only; dry-run execution is not real fulfillment, dry-run result is not an effect receipt, dry-run receipt is not proof of host mutation, and real actuation remains deferred.

Downstream dry-run proof link: [Host Dry-Run Effect Verification / Audit Closure Wing](host_dry_run_audit_closure_wing.md). It preserves the boundary that dry-run closure is not fulfillment, effect receipt, real host postcondition check, rollback, production audit, or actuation.

Proof path: docs/architecture/host_dry_run_audit_closure_wing.md


## Real effect capability admission link

See [Host Real Effect Capability Admission Wing](host_real_effect_capability_admission_wing.md) (`docs/architecture/host_real_effect_capability_admission_wing.md`): dry-run closure does not automatically permit real effects; real effect admission is not implementation, the admission decision does not authorize implementation or execution, the plan scaffold does not start implementation, cooling/hardware control remains blocked by default, and real actuation remains deferred.

The authority ladder later reaches the [Host Local Diagnostic Effect Pilot Wing](host_local_diagnostic_effect_pilot_wing.md), the first explicit diagnostic artifact write effect.

Later bounded real-effect proof organs include the [Host Local Diagnostic Effect Pilot Wing](host_local_diagnostic_effect_pilot_wing.md) and its [exact artifact rollback pilot](host_local_diagnostic_exact_rollback_pilot_wing.md); both remain explicit and narrow.

The later [Host Local Effect Transaction Ledger Wing](host_local_effect_transaction_ledger_wing.md) remains downstream of authorization, real-effect admission, the local diagnostic effect pilot, and exact rollback; it is metadata-only transaction integrity, not new authority.

See also: [Host Steward / Delegated Runner Boundary Wing](host_steward_delegated_runner_boundary_wing.md) (`docs/architecture/host_steward_delegated_runner_boundary_wing.md`) for the next authority boundary after the local effect transaction ledger. It models broad top-level host-steward authority without granting delegated runners ambient authority.
