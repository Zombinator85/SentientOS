# Production local-model activation authority

This page defines law for the bounded selection-state capability
`local_model_production_activation`. Its sole eligible principal is
`deterministic_local_model_activation_controller`. The blessed origin is the
operator-accountability doctrine in
[`AGENTS_DOCTRINE_ARCHIVE.md`](../AGENTS_DOCTRINE_ARCHIVE.md): privilege must be
explicit, witnessed, bounded, revocable, and fail closed. Definition eligibility
is not a grant, approval, control-plane admission, or runtime authority.

## Meaning and admitted effects

**Activation** means publishing one exact commissioned model identity as the
installation's authoritative selected active-model state. It does not load or
retain a model, start chat or serving, boot-load, perform inference, or grant
inference authority. Commissioned is not activated; activated state is not a
loaded model, serving process, or inference authority.

The duplicate-free future effect set is:

1. `exact_operator_approval_evidence_read`
2. `exact_authoritative_deployed_catalog_proof_read`
3. `exact_hardened_local_model_commissioning_receipt_read`
4. `exact_commissioned_artifact_identity_read`
5. `exact_activation_intent_read`
6. `exact_current_activation_state_read`
7. `authoritative_active_model_compare_and_swap`
8. `local_model_activation_receipt_write`

Goals must affirmatively require **explicit operator approval**, **authoritative
deployed catalog**, **hardened commissioning receipt**, and **exact prior
activation state**. Negated, missing, ambiguous, wildcard, or blind-overwrite
forms fail closed. Acquisition, commissioning, model load, serving, boot load,
inference, generic filesystem/configuration/network/provider/tool/memory/action
authority, arbitrary paths, repository mutation, and self-grant are outside the
capability.

`AuthorityClass.MODEL_ACTIVATION` is a new non-effectful schema identity, distinct
from `MODEL_COMMISSIONING`, `MODEL_ARTIFACT_ACQUISITION`,
`LOCAL_MODEL_INFERENCE`, and `PRIVILEGED_OPERATOR_CONTROL`. A future controller
must obtain an exact `MODEL_ACTIVATION` `ALLOW` before state mutation. This
declaration neither requests nor consumes that admission.

The existing `persistent_runtime_activation_controller` belongs to a separate
persistent runtime lifecycle station; name similarity does not make it eligible
to publish authoritative local-model selection state. Commissioning, acquisition,
catalog deployment/authorization, publication, stochastic/model, maintenance,
curator, generic chat, and generic runtime principals are likewise denied.

## Immutable intent and exact transition

Before mutation, future runtime must construct
`sentientos.local_model_activation_intent:v1`. It binds schema and deterministic
intent identity/digest; the exact principal, capability, and effects; correlation
and installation identities; canonical activation and current catalog custody;
catalog semantic/proof digests and deployment receipt lineage; hardened
commissioning receipt, commissioning intent, and plan lineage; model, artifact,
SHA-256, byte size, exact commissioned custody path, route, engine, backend,
runtime, and interpreter identities; exact future load configuration and
authority-map identity/digest; expected prior state; deterministic intended new
state payload/digest; activation-receipt custody; and explicit false
`model_load_performed`, `serving_started`, and `inference_performed` fields. The
intent is neither approval nor activation.

Compare-and-swap is mandatory. Genesis uses exactly `ABSENT`; replacement uses
the exact semantic digest of current authoritative activation state. Empty,
`*`, `current`, `latest`, `any`, `wildcard`, omitted, and blind-overwrite prior
states are invalid. Approval expectation and the controller's independent
observation remain distinct; mismatch causes no state write.

Immediately before mutation the controller must independently call
`construct_authoritative_catalog_consumer_proof(authenticated_installation_handle)`.
The commissioning receipt's catalog proof must exactly equal that current proof;
a changed deployment invalidates historical commissioning evidence even when
bytes match. There is no implicit cross-deployment rebinding.

Only strictly verified `sentientos.local_model_commissioning_receipt:v3` evidence
qualifies. Verification covers deterministic receipt identity/digest, execution
principal/capability/effects, intent and external approval lineage,
`MODEL_COMMISSIONING` and nested smoke `LOCAL_MODEL_INFERENCE` admission lineage,
hardened acquisition and current-catalog lineage, artifact and runtime identity,
and false `model_left_loaded`, `activated`, and
`serving_authority_granted`. Synthetic production evidence and adjacent effects
are rejected. Legacy v2, bytes alone, and status text do not qualify.

The controller must also re-read the exact artifact in canonical commissioned
custody and match artifact ID, SHA-256, and byte size. Missing or changed bytes
fail closed without state publication. This verification constructs no model.

## External approval and custody

Future immutable `sentientos.local_model_activation_approval:v1` evidence binds
its deterministic ID/digest, operator and provenance, `approved` status, exact
principal/capability/effects, correlation, intent ID/digest, installation and
activation custody, current catalog custody/proof and deployment receipt,
commissioning receipt, model/artifact/route/runtime identities, artifact hash and
size, expected prior state, intended state digest, approval time, bounded validity,
and synthetic-test posture. It permits no wildcard. The controller cannot create
genuine approval; `approve=True`, `--approve`, `--force`, `--yes`, `--trust`, and
`--blind-overwrite` are not approval mechanisms.

Custody is installation-scoped through an authenticated `InstallationStateHandle`,
never a caller-selected root:

```text
local-model/activation/
    activation.lock
    active.json
    transactions/
    receipts/
```

It provides one fixed lock and authoritative state per installation,
deterministic state/transaction identity, protected traversal, no symlink
substitution, durable crash-recoverable replacement, exact prior-state CAS, and
immutable receipts. Mutable `active.json` changes only through the governed
controller. Activation custody is not the repository, artifact escrow, catalog
custody, curator escrow, or commissioning receipt directory.

## Hardened state and receipt

Authoritative state uses
`sentientos.local_model_activation_state:v2`, not legacy v1. It binds schema,
status and semantic digest; installation/custody; intent and commissioning
receipt IDs/digests; current catalog proof; model/artifact/hash/size; route,
engine, backend, runtime, interpreter, load configuration, authority-map identity;
correlation and generation identity; a non-circular receipt reference if feasible;
and false `model_loaded`, `serving_started`, and `inference_performed`. It means
only that this commissioned identity is selected.

Immutable `sentientos.local_model_activation_receipt:v1` binds receipt
ID/digest; principal, capability, effects, approval, and `MODEL_ACTIVATION`
admission; correlation, installation, custody and intent; expected and observed
prior states; resulting state and current catalog proof; commissioning lineage;
model/artifact/route/runtime and exact hash/size; successful CAS and durable
publication; and false model-load, serving, and inference postures. It proves
only completion of the activation-state transition—not load, boot-load, server
health, serving, or inference.

## Legacy and deferred boundaries

Current legacy `activate(receipt, activation_path)` consumes the legacy
commissioning receipt schema, accepts a caller-selected destination, and replaces
a mutable activation object without this approval, custody, CAS, or
`MODEL_ACTIVATION` contract. Hardened commissioning v3 remains intentionally
incompatible. Current `load_activation(path)` then reads legacy state, constructs
the model, and reconstructs its authority map. Neither function is changed here.

Loading belongs to a separately reviewed activated-model consumer:

```text
hardened activation state -> governed consumer -> current-state/catalog/receipt/
artifact/runtime revalidation -> exact model load -> governed inference serving
```

Approval consumption, catalog and artifact revalidation, v3 receipt consumption,
`MODEL_ACTIVATION` admission, fixed custody, exact CAS, crash finalization,
receipt publication, and a read-only current-state verifier are implemented.
Genuine real-world approval and first activation, and every load/serving/boot
lifecycle, remain deferred. The implementation creates no model, performs no
inference, starts no serving process, and grants no consumer authority.

The frozen future invariant is: current authoritative catalog + hardened
commissioning v3 + exact artifact + exact intent + external approval + exact
prior state + `MODEL_ACTIVATION` admission yields one installation-scoped CAS and
one immutable receipt—and still does not load, serve, or infer.
