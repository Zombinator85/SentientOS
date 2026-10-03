# Publisher-attempt identity evidence producer authority contract

Schema: `sentientos.production_chat_resource_provisioning_request_attempt_identity_authority_contract:v1`.

This governance-only contract freezes a candidate authority definition. A candidate is not a registered definition; registration is not a runtime grant; a runtime grant is not execution. The candidate remains absent from canonical `AUTHORITY_DEFINITIONS`, has no operator approval, and cannot emit identity evidence.

## Separate, bounded authority

The registered request publisher cannot simply be widened: its five effects govern request and receipt publication custody, while pre-effect lifecycle evidence is a different mutation with a different principal and custody root. The candidate capability `production_chat_resource_provisioning_request_attempt_identity_evidence_create`, principal `deterministic_production_chat_resource_provisioning_request_attempt_identity_evidence_producer`, and subsystem `causal_resource_principal_architecture` therefore stand alone. Request-publication authority is not attempt-identity lifecycle-evidence authority in either direction, and neither definition inherits the other's effects.

Its exact effects are:

1. `read_exact_pre_effect_production_resource_provisioning_request_publication_intent` — consume only the publisher's already validated installation, provisioning, exact request-byte/binding, request digest, storage hash/size, inert intent, publisher-authority, and frozen-contract bindings; it permits neither source discovery nor reconstruction.
2. `establish_one_production_resource_provisioning_request_publication_attempt_identity` — establish one fresh bounded non-placeholder invocation identity under the frozen attempt-ID law; no caller selection, retrospection, publication, closure, or process/lock/PID identity.
3. `create_only_installation_state_production_resource_provisioning_request_attempt_identity_evidence` — create exactly `local-model/resource-provisioning-request-attempts/<publication_attempt_id>/identity.json` in authenticated installation state, with no alternate destination, overwrite, repair, deletion, cleanup, retry, or request-custody mutation.
4. `finalize_production_resource_provisioning_request_attempt_identity_evidence` — complete the immutable canonical artifact and digest/provenance binding before publication-custody mutation; no publisher closure or recovery receipt.

These effects reference, and do not redefine, the evidence schema, fields, digest law, attempt-ID law, custody path, or provenance requirements frozen by the [attempt-identity contract](production_chat_resource_provisioning_request_attempt_identity_contract.md), digest `e8ec7ab9408ca3303c07f9a7878f89a4f718cec0f54c7e7a8c8b0158179823c0`.

## Admission and approval boundary

A later request must affirm all five phrases: `create-only publisher attempt identity evidence`; `exact pre-effect request and intent binding`; `before first publication custody mutation`; `independently verifiable lifecycle provenance`; and `no request publication or recovery authority`. The machine contract freezes the complete forbidden phrase set and these approval requirements: independent operator approval evidence; exact definition digest binding; exact publisher attempt identity contract digest binding; exact existing publisher authority definition binding; exact installation provisioning request and intent binding; create-only fixed attempt identity evidence custody; identity evidence completed before first publication custody mutation; independently verifiable lifecycle provenance; production non-synthetic evidence posture; and no request publication receipt terminal closure or recovery authority.

The canonical candidate definition digest is `ad219f43186a8a173e31dda428cff068c5ee2643211284dacf391f858def3b6d`. The existing publisher definition remains unchanged at `349058b7e6959c06bfae1a8acabd01c6c022245c6fd404e63535cac6ed608cf5` with its existing five effects.

## Ordering and provenance remain future work

Definition eligibility does not prove ordering. Admission does not prove ordering. Artifact creation alone does not prove ordering. A future implementation and independent verifier must mechanically prove completion before the first durable request-publication custody mutation. The producer cannot authenticate its own provenance: `attempt_identity_evidence_producer != independent_attempt_identity_provenance_verifier`, and self-verification is insufficient.

The frozen future registrar handoff is template-only and uses `register_authority_definition(...)` with inert runtime fields. Operator evidence ID, identity, and evidence digest are deliberately unsupplied. Until a separate operator-approved registration task, later admitted implementation, fixed-custody writer, and independent provenance mechanism exist, no production `identity.json` may be emitted.
