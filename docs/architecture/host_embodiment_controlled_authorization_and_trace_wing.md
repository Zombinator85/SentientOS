# Host Embodiment Controlled Authorization + Trace Wing

This wing follows the [Authorization Review Wing](host_embodiment_authorization_review_wing.md). It defines the controlled authorization grant contract and a reviewer-facing end-to-end trace across the non-mutating host-embodiment ladder.

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
