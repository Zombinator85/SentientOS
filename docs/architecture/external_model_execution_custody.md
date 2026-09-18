# External-model execution custody

The execution-custody pipeline is deterministic and fail-closed:

`proposed invocation -> configured service -> bounded request -> opaque credential-use custody -> externally supplied admission evidence -> isolated transport port -> result custody -> durable receipt`.

The service catalog is positive configuration governance. Each versioned entry binds one stable service identity to one exact HTTPS endpoint, a sorted bounded model set, an optional opaque credential-reference identity, enablement, provenance, and a configuration digest. Catalog JSON is canonical, digest-bound, atomically replaced, and strictly rejected when malformed or corrupt. Configuration survives restart; it contains no secret value. **Configured does not mean authorized.**

Credential handles contain only a service-bound reference, intended-use class, provenance, and non-secret availability observation. A credential reference is not a secret, and use custody is not credential administration. No repository-sanctioned live external-provider secret resolver is connected here: only the narrow future `SecretResolutionPort` contract exists. It supplies no enumeration, inspection, creation, modification, rotation, export, or environment-variable access.

The controller validates the catalog, existing request custody, opaque handle, and explicit externally issued admission evidence. Admission binds the deterministic principal, exact service and endpoint, request digest, configuration digest, authority identity, and sequence validity. The controller has no admission issuer: admission consumed does not mean admission issued, and reconstructed configuration or receipts never become authority.

The isolated transport receives only an admitted, configuration-bound invocation. The sole production implementation is the null transport. It reads no secret, opens no socket, imports no provider client, makes no request, and reports `unavailable` with transport not attempted and provider not responded. Transport available would not mean transport authorized. Transport attempted is distinct from transport succeeded; response received is distinct from response trusted by cognition.

Receipts are canonical JSON, atomically persisted, deterministically ordered, and hash-linked. Restart reconstruction strictly verifies schema, ordering, and links. A transport attempt or provider response can only be derived from transport evidence; synthetic fake evidence remains visibly synthetic and cannot claim a real effect. Persistence failure is terminal rather than being treated as success.

## Capability readiness reassessment

Positive service governance, exact endpoint enforcement, opaque credential-use custody, deterministic unempowered principal identity, bounded request and response custody, admission consumption without self-admission, an isolated transport port, and durable receipt persistence now exist. Actual live secret resolution and live transport do not exist.

Before `external_model_inference` can responsibly be prepared again, an operator-governed secret-use resolver (without administration/export), an independently owned authority definition and issuer integrated with current admission machinery, freshness/revocation policy, an audited isolated real transport adapter, response trust policy, production failure/rollback and monitoring, and operator approval are still required. The superseded proposal must bind the configured-service/configuration digest, exact endpoint, principal, request digest, opaque credential-use identity, freshness/revocation semantics, transport evidence, and durable receipt chain; it must not treat configuration, credential availability, validation, or transport availability as authority. This document neither regenerates nor approves that definition.
