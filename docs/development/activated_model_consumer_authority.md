# Activated-model consumer authority

This page defines governance law for `local_model_production_serving`. Its sole
eligible principal is `deterministic_activated_model_serving_controller`. Its
blessed origin is the operator-accountability and witnessing law in
[`AGENTS_DOCTRINE_ARCHIVE.md`](../AGENTS_DOCTRINE_ARCHIVE.md). Definition eligibility is not a grant or inference call. The implemented controller
still requires exact runtime control-plane admission for every new session.

## Exact boundary

The production consumer begins with the authenticated **current** hardened
activation state, not an activation file, model path, legacy activation bundle,
autoload choice, or caller-selected root. Immediately before load and session
publication it must revalidate the exact activation receipt, authoritative
deployed-catalog proof, hardened commissioning receipt, artifact identity and
bytes, and runtime identity. A missing, stale, contradictory, or changed link
fails closed.

The duplicate-free future effect set is:

1. `authenticated_current_hardened_activation_state_read`
2. `exact_current_activation_receipt_read`
3. `exact_authoritative_deployed_catalog_proof_read`
4. `exact_hardened_local_model_commissioning_receipt_read`
5. `exact_activated_artifact_identity_and_bytes_read`
6. `exact_activated_runtime_identity_read`
7. `bounded_exact_activated_model_load`
8. `authoritative_serving_session_bind`
9. `stale_serving_session_invalidation`
10. `local_model_serving_session_receipt_write`

Eligible goals must affirmatively require **authenticated current hardened
activation state**, **current catalog provenance**, **exact artifact and runtime
identity**, **activation-change invalidation**, and **separate local model
inference**. Inexact effects, another principal or subsystem, arbitrary or legacy
paths, stale evidence, skipped currentness, silent stale-model retention, chat or
boot integration, generation, and adjacent authority fail closed.

## One session-establishment authority, separate generation authority

Current architecture requires the loaded object and production-current serving
session to share one exact activated identity. Loading without atomic session
binding must not make a model production-current, and session binding must not
accept a caller-supplied previously loaded object. Therefore this governance
contract keeps exact load plus serving-session binding/invalidation in one
bounded `AuthorityClass.MODEL_SERVING`, rather than creating a reusable loading
authority that could escape currentness checks.

`MODEL_SERVING` is a non-effectful schema identity distinct from
`MODEL_ACTIVATION`, `MODEL_COMMISSIONING`, `MODEL_ARTIFACT_ACQUISITION`, and
`LOCAL_MODEL_INFERENCE`. Activation remains selection only. Serving admission
does not authorize generation: every generation call must independently obtain
`LOCAL_MODEL_INFERENCE` admission through the existing governed invocation path.

A future serving session must bind the activation state's semantic digest and
the revalidated model, artifact, hash, size, route, engine, backend, runtime,
interpreter, load-configuration, authority-map, catalog-proof, commissioning,
and activation-receipt identities. Before use it must prove that binding still
matches authenticated current activation. An activation change makes the old
session non-current and requires deterministic invalidation; the old model may
not silently continue as production-current.

## Implemented serving establishment and inference handoff

`ProductionServingController` consumes only an authenticated installation handle and
the canonical activation verifier. It obtains exact `MODEL_SERVING` admission before
constructing `ExactRuntimeLocalModel`, checks the observed ready identity, re-verifies
current activation after the load race, and then publishes an opaque deterministic
session plus immutable installation-scoped receipt and `/logs/privileges/` witness.
Currentness inspection re-verifies activation and unloads sessions after activation
change or worker death. The receipt explicitly records that inference was not performed
and that local-model inference authority was not granted.

Serving keeps four identities separate. The activated-model identity names the exact
authenticated selection and evidence chain. A caller must supply a bounded, explicit,
non-placeholder serving-establishment operation identity for each requested load
attempt. The control-plane correlation deterministically binds both of those identities,
so admission dedupe prevents replay of one operation while a new operation can be
separately admitted after a legitimate unload even when the activation is unchanged.
The resulting serving-session identity names that particular admitted load lifetime and
is carried into its receipt and invalidation evidence; it is not derived from activation
alone. A serving-backed inference correlation is the fourth, independent identity and
requires separate `LOCAL_MODEL_INFERENCE` authority for every generation. The bridge
reconstructs the commissioning authority map, proves its digest and exact loaded
identity, and binds its request to all three upstream identities and their evidence. It
rechecks currentness after admission immediately before generation and again after it;
a pre-effect change prevents generation, while a post-effect change preserves the
truthful effect receipt, suppresses stale output, and invalidates the old lifetime.

The four identities are therefore activation identity, serving-operation identity,
serving-session/load-lifetime identity, and inference request/correlation identity. Only
the fourth is governed by `LOCAL_MODEL_INFERENCE`; neither `MODEL_SERVING` nor its receipt
grants generation. Establishment never infers and the bridge never silently reloads or
retries.

Explicit production chat composition is implemented. It parses an installation identity,
opens only `InstallationStateRegistry.system()` custody, establishes one caller-named
serving operation, and installs the opaque serving-backed inference bridge. Every chat
turn retains its own conversation/turn correlation and independently admitted
`LOCAL_MODEL_INFERENCE` request. Durable conversation identity binds stable activation,
artifact, runtime, authority-map, and observed-model provenance while deliberately
excluding serving operation and session identities. Activation change, worker death, or
currentness failure invalidates the lifetime and fails chat closed; it never autoloads,
selects simulation, or silently re-establishes serving.

Echo/null use is available only through affirmative development/test composition.
Canonical boot integration, automatic loading or recovery, one-click installation,
providers, network access, tools, actions, repository mutation, and performance tuning
remain deferred. The session and chat service expose no raw model, backend, worker, or
generic production invoker.
