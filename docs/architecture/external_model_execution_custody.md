# External-model execution custody

The execution-custody pipeline is deterministic and fail-closed:

`proposed invocation -> configured service -> bounded request -> opaque credential-use custody -> externally supplied admission evidence -> isolated transport port -> result custody -> durable receipt`.

The service catalog is positive configuration governance. Each versioned entry binds one stable service identity to one exact HTTPS endpoint, a sorted bounded model set, an optional opaque credential-reference identity, enablement, provenance, and a configuration digest. Catalog JSON is canonical, digest-bound, atomically replaced, and strictly rejected when malformed or corrupt. Configuration survives restart; it contains no secret value. **Configured does not mean authorized.**

Credential handles contain only a service-bound reference, intended-use class,
provenance, and non-secret availability observation. A credential reference is
not a secret, and a configured reference is not permission to use it.
`GovernedCredentialResolver` accepts the complete request and admission, then
re-resolves and verifies the enabled service, endpoint, model, configuration and
request digests, principal, capability, effect, and service-bound handle through
`RuntimeAdmissionVerifier`. There is intentionally no `resolve(ref)` API.

The read-only production backend uses the platform OS credential service through
Python `keyring`: service name `sentientos.external_model.<service_id>`, username
the opaque credential reference. An operator provisions that item outside model
invocation using host keyring administration. The resolver/controller provides
no provisioning, enumeration, mutation, rotation, deletion, or export. Storage
survives restart when the same account keyring is unlocked and catalog and
admission custody reconstruct successfully. Missing, locked, unavailable, or
corrupt keyring state fails closed, with no environment/plaintext fallback.

After verification, secret text is converted to a mutable buffer, exposed as a
read-only view only during the future transport callback, then overwritten.
Python and OS keyrings can retain intermediate immutable copies, so guaranteed
memory erasure is not claimed. Secret bytes are not persisted in requests,
results, receipts, logs, representations, JSON, or exception messages.

The controller validates the catalog, existing request custody, opaque handle, and explicit externally issued admission evidence. Admission binds the deterministic principal, exact service and endpoint, request digest, configuration digest, authority identity, and sequence validity. The controller has no admission issuer: admission consumed does not mean admission issued, and reconstructed configuration or receipts never become authority.

The isolated transport receives only an admitted, configuration-bound
invocation. The sole production implementation is the null transport. It does
not resolve a credential, opens no socket, imports no provider client, makes no
request, and reports `unavailable`. Runtime admission is not a resolved
credential; a resolved credential is not successful transport; and successful
transport is not a response trusted by cognition.

Receipts are canonical JSON, atomically persisted, deterministically ordered, and hash-linked. Restart reconstruction strictly verifies schema, ordering, and links. A transport attempt or provider response can only be derived from transport evidence; synthetic fake evidence remains visibly synthetic and cannot claim a real effect. Persistence failure is terminal rather than being treated as success.

## Capability readiness reassessment

Positive service governance, exact endpoint enforcement, opaque credential-use
custody, deterministic unempowered principal identity, bounded request and
response custody, admission consumption without self-admission, an isolated
transport port, and durable receipt persistence exist. Runtime grant policy and
runtime admission now provide definition-to-grant-to-admission narrowing,
expiry, revocation, supersession, and exact principal/effect/subject/request
configuration bindings.

The current non-granting `external_model_inference` definition is prepared in
[`governed_external_model_authority_proposal.md`](../development/governed_external_model_authority_proposal.md).
Production-capable governed credential resolution now exists. Live transport,
operational feasibility, provider authentication framing, response validation
and trust policy, and operator-specific keyring provisioning guidance remain
prerequisites. The registered authority definition is unchanged; this resolver
creates neither grants nor admissions. `external_model_inference` is therefore
not production-ready. Configuration,
credential availability, validation, admission, and transport availability
must never be treated as interchangeable authority or success claims.
