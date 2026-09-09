# Production local-model commissioning authority

This document records governance and the separately admitted hardened commissioning
runtime. The authority consumer never creates approval, activation, acquisition,
catalog mutation, serving authority, or provider authority. The
capability remains `local_model_production_commissioning`; registry metadata is
not task-authority admission, task-authority admission is not operator approval,
and operator approval is not control-plane admission.

The blessed origin is the repository's operator-accountability doctrine in
[`AGENTS_DOCTRINE_ARCHIVE.md`](../AGENTS_DOCTRINE_ARCHIVE.md): privilege must be
documented, witnessed, bounded, revocable, and fail closed. The admitted future
principal is only `deterministic_local_model_commissioning_controller`. The model,
acquisition and deployment controllers, maintenance worker, activation controller,
and generic chat/runtime callers cannot authorize commissioning.

## Exact admitted transition

The definition requires this duplicate-free effect set:

1. `exact_operator_approval_evidence_read`
2. `exact_authoritative_deployed_catalog_proof_read`
3. `exact_hardened_model_artifact_acquisition_receipt_read`
4. `exact_commissioning_intent_read`
5. `bounded_zero_generation_gguf_compatibility_construction`
6. `bounded_exact_local_model_load`
7. `bounded_commissioning_smoke_inference`
8. `local_model_commissioning_receipt_write`

Future goals must affirmatively require **explicit operator approval**,
**authoritative deployed catalog**, and **exact acquired artifact identity**.
Negated or missing preconditions fail closed. These narrow effects grant no
generic filesystem, process, network, model-execution, serving, activation,
tool, memory, action, provider, credential, or repository authority. Reading an
acquisition receipt is not acquisition authority; an exact load is not
activation; a bounded commissioning smoke inference is not serving authority.

`AuthorityClass.MODEL_COMMISSIONING` is the runtime admission class for
the whole exact transition. The hardened runtime obtains its exact `ALLOW`
before the first commissioning effect. The one-shot smoke inference must also
satisfy the existing governed `LOCAL_MODEL_INFERENCE` boundary. Commissioning
admission and inference admission are distinct and neither substitutes for the
other. `MODEL_ARTIFACT_ACQUISITION` cannot be reused for commissioning, and
`PRIVILEGED_OPERATOR_CONTROL` would be overbroad. The normal `ControlPlaneKernel.admit` path mediates that parent admission.

## Pre-effect intent and approval

Compatibility currently precedes the final commissioning plan, while its
vocab-only GGUF probe constructs a model despite producing zero semantic
generations. A future deterministic
`sentientos.local_model_commissioning_intent:v1` must therefore exist before
that construction. It must bind installation identity; catalog custody identity;
current authoritative consumer-proof digest; deployment receipt ID/digest;
hardened acquisition plan digest and receipt ID/digest; model and artifact IDs;
artifact SHA-256, byte size, and exact custody path; route and runtime IDs;
interpreter identity; backend family; exact compatibility-probe contract; exact
load bounds; exact one-shot smoke contract; exact output custody identity; and
correlation ID.

Externally supplied immutable approval must bind exactly that intent and
transition: operator identity; approval evidence ID/digest; the exact principal,
capability, and effect set; correlation and installation identities; catalog
custody and current proof digest; deployment and hardened acquisition receipt
IDs/digests; intent digest; model/artifact/route/runtime identities; artifact
hash and size; compatibility, load, and smoke bounds; output custody; and a
bounded validity interval. Wildcards are forbidden. The controller may not
manufacture genuine approval, and no cryptographic-human-identity claim is made
until a mechanism proves it.

Both external approval and exact `MODEL_COMMISSIONING` control-plane `ALLOW`
must exist **before** zero-generation GGUF construction. A compatibility receipt
may narrow and prove the approved intent but never widen it.

## Current catalog and acquisition evidence

Immediately before the first effect, future runtime must call
`construct_authoritative_catalog_consumer_proof(authenticated_installation_handle)`
against canonical installation-scoped custody and require exact equality with
the provenance in hardened acquisition evidence. Saved selection, plans,
receipts, and reconstructed chain are historical evidence, not currentness.
Timestamps and caller-supplied catalog bytes cannot establish current custody.
If deployment changed, previously acquired bytes remain historical custody but
cannot be commissioned unless the current authoritative catalog independently
binds the same exact artifact.

Only `sentientos.local_model_artifact_acquisition_receipt:v2` qualifies. Future
validation must independently verify schema and semantic digest; authoritative
deployed provenance; artifact identity/hash/size; acquisition
principal/capability/effect lineage; operator-approval and acquisition
control-plane lineage; and completed verified-artifact posture. Legacy v1 and
mere escrow-byte existence fail closed. Acquisition conveys no commissioning,
activation, or inference claim.

## Truthful current posture and next boundary

The hardened consumer builds `sentientos.local_model_commissioning_intent:v1`
before construction and binds current authenticated catalog custody, acquisition
receipt v2, exact contracts, and fixed installation custody. Acquisition v2 has no
canonical receipt ID, so its strictly verified semantic digest is used unchanged as
its identity; historical evidence is not mutated.

External approval and exact parent `MODEL_COMMISSIONING` ALLOW precede the first
vocab-only construction. The independently governed smoke uses a deterministic,
distinct child correlation and the same kernel. The model is closed in cleanup before
`sentientos.local_model_commissioning_receipt:v3` is durably created under
`local-model/commissioning/receipts/`. The production CLI consumes approval and an
authenticated installation identity; it exposes neither `--confirm-plan-digest`, an
arbitrary output root, nor standalone compatibility construction.

Legacy v2 authorization/commissioning APIs remain named historical compatibility
surfaces and are not consumed by `commission_production`. Legacy activation accepts
only v2 receipts, so hardened v3 evidence cannot cross the separately unhardened
activation boundary. Registry status remains `partial`: genuine real-world approval
and commissioning events, activation authority, serving/boot lifecycle, maintenance
E2E, and performance tuning remain deferred. Acquired is not commissioned;
commissioned is not activated; a receipt is not unrestricted serving authority.
