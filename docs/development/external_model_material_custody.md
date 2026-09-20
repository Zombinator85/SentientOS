# External-model material custody

## Boundary

An invocation request digest is not request material. A response digest is not
response material, and response material is not a trusted response. Definition,
grant, admission, execution, provider response, and trusted cognition input
remain distinct states. Material availability grants none of them.

`GovernedRequestMaterialResolver` asks a narrow source for one complete
invocation binding: request, service, endpoint, model, credential-reference
identity, request-binding digest, configuration digest, admission identity, and
expected payload digest. There is no digest-only or arbitrary-key lookup. The
production `UnavailableRequestMaterialSource` fails closed; no filesystem,
environment, database, or global request store is manufactured here.

Before exposure, the resolver repeats configured-service enablement, exact
endpoint, model scope, credential-reference, request-envelope, request-binding,
runtime-admission capability/principal/effect/subject/freshness/revocation, and
request/configuration-digest checks. It then bounds request material to 1 MiB
and independently hashes its bytes. A transport receives only a read-only view
during its callback.

The material-aware provider-neutral seam may return an owned response buffer
beside transport evidence. Execution custody requires an attempted transport
and a response claim, bounds the response to 4 MiB, independently computes its
digest, compares it with transport evidence, and offers a read-only view only to
an explicit callback. `UntrustedResponseMetadata.epistemic_status` is always
`untrusted_external_data`; there is no trusted flag, global response store,
cognition integration, prompt chaining, or memory write.

Owned mutable request and response buffers are overwritten on success and
exception paths. This is a best-effort clearing guarantee for those exact
`bytearray` objects, not a promise of physical memory erasure: Python, callback
code, libraries, and the operating system may retain copies. Raw material is
never added to catalogs, admission/grant/authority ledgers, result envelopes,
receipts, audit JSON, provenance, or landing evidence. Only identities,
digests, and truthful transport metadata are durable.

The null transport remains the sole production transport. It resolves neither
request material nor credentials, attempts no effect, and reports truthful
unavailability. `CredentialedExternalModelTransport` remains as compatibility
for its existing execution-custody tests and potential current importers; new
material-capable implementations use `MaterialExternalModelTransport`.

## Implementation status

Implemented: authority-definition registration, runtime grant and admission
machinery, request metadata custody, governed read-only OS-keyring credential
resolution, bounded request/response material custody, null transport, and
durable hash-linked receipt/evidence custody.

Not implemented or active: live HTTPS transport, provider-specific
authentication or request framing, a live provider effect, network operational
feasibility policy, cognition response-trust policy, or automatic cognition
consumption of external responses. External-model inference is not
production-ready.
