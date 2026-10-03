# Production chat resource provisioning request-publication contract

## Status and authority boundary

This document preserves the frozen pre-registration design and handoff while recording
the current repository state: its exact authority definition is now canonically
registered and the bounded create-only runtime publisher is implemented in
`sentientos.production_chat_resource_provisioning_request_publisher.py`. The bounded
read-only published-request consumer is implemented in
`sentientos.production_chat_resource_provisioning_request_consumer.py`. Request publication is not
provisioning-bundle creation, allocation issuance, operator confirmation, ordinary
startup, model inference, or runtime-effect admission. In particular,
`production_chat_resource_provisioning_request_publish` !=
`production_chat_resource_provisioning_bundle_create`. The former prepares durable,
verified operator-request custody for a later `prepare/create` act. The latter may issue
one allocation and create the final bundle. Neither implies the other.

The normative machine artifact is
`architecture/production_chat_resource_provisioning_request_publication_contract.json`,
schema `sentientos.production_chat_resource_provisioning_request_publication_contract:v1`.

## Exact inputs and genuine verification

The publisher receives only an authenticated `InstallationStateHandle`, a
validated `resource_provisioning_id`, the exact pre-existing bytes of one canonical
`CausalResourcePrincipal`, `RootPrincipalIssuerProvenance`, trusted issuer catalog,
principal revocation registry, and `GovernedLocalModelResourcePolicy`; exact
`GovernedLocalModelResourceBounds`; canonical requested validity endpoints; and a
trusted publication-time source. Filesystem source paths, chat/request/session/memory
data, model output, and startup-generated identity are not authority-bearing inputs.

Before destination mutation, `CryptographyEd25519RootIssuerSignatureVerifier` and
`RootIssuerProvenanceVerifier` combine the canonical principal, provenance, and
`ReadOnlyTrustedIssuerCatalog` into verifier-created
`AuthenticatedRootPrincipalEvidence`. `PrincipalCurrentnessVerifier` then combines that
evidence, the same principal, and `ReadOnlyPrincipalRevocationRegistry` into
`CurrentAuthenticatedRootPrincipalEvidence`. The exact policy is validated. Caller-made
authenticated/current evidence and trust shortcuts are forbidden. The publisher has no
`RootIssuerPrivateKeyCustody`, signer, or raw issuer seed; it never calls `mint_root` or
`mint_root_with_provenance`, signs provenance, or administers trust, currentness, or
policy.

One trusted canonical UTC second-resolution `publication_time` is used for principal
validity, provenance authentication, issuer-trust validity, principal currentness, and
policy currentness. It is not allocation, later actuator-create, or inference time.
Requested bounds must be structurally valid and no broader than the supplied policy.
Requested times must be canonical UTC seconds with `requested_not_before <
requested_not_after`; neither check issues or reserves entitlement.

## Exact bytes, request, and custody

All five artifact byte strings are preserved without normalization or JSON
reserialization. Each is embedded as exactly `encoding`, `sha256`, and `data`, with
`encoding = base64url`, lowercase SHA-256 over decoded bytes, and canonical unpadded
base64url data. Validation may parse the bytes; publication preserves them.

The request has exactly the current actuator fields: `schema_version`,
`installation_identity`, `resource_provisioning_id`, the five `*_artifact` fields,
`requested_bounds`, `requested_not_before`, `requested_not_after`, and `request_digest`.
It uses `sentientos.production_chat_resource_provisioning_request:v1`, introduces no
translation or second schema, and must round-trip through `load_provisioning_request`.
`request_digest` is lowercase SHA-256 over canonical JSON of all other fields using
UTF-8, sorted keys, separators `","` and `":"`, `ensure_ascii=true`, and finite JSON.
The inert `prepare_provisioning_intent(request_bytes)` must produce one deterministic
intent without confirmation, execution, or state access.

For authenticated installation I and bounded ID P, custody is fixed at
`local-model/resource-provisioning-requests/P/`, containing only `request.json` and
`publication-receipt.json`; the authenticated installation-state lock is
`local-model/resource-provisioning-request-locks/P.lock`. There are no caller-selected
destinations and no paths in either artifact. The same P may later name
`local-model/resource-provisioning/P/`, but publishing P only permits later operator
consideration; it does not create that final destination.

The lock spans unused-destination inspection and both creates; a process-local mutex is
insufficient. An empty directory may be tolerated only when installation-state directory
creation requires it. Any object burns the ID for automatic retry. At most one request
generation exists per installation and P: no overwrite, merge, repair, deletion,
amendment, replacement, renewal, or automatic retry. Changed material requires a new P.

## Receipt, ordering, and partial failure

The receipt schema is
`sentientos.production_chat_resource_provisioning_request_publication_receipt:v1`. Its
exact fields are: `schema_version`, `installation_identity`,
`resource_provisioning_id`, `request_digest`, `intent_digest`, the five raw artifact
`*_sha256` bindings, `principal_id`, `principal_binding_digest`, `provenance_digest`,
catalog version/digest, revocation-registry version/digest, `resource_policy_digest`,
`verified_at`, `authority_definition_digest`, and `receipt_digest`. It contains no paths,
private-key material, allocation identity/digest, or remaining-call claim. The authority
binding must equal the exact registered publisher-definition digest. `receipt_digest` is
lowercase SHA-256 over every other receipt field under the same finite canonical-JSON
law as the request.

The exact order is: validate all bytes; verify principal/provenance/trust/currentness and
policy; validate bounds and validity; acquire the exact per-ID lock; prove unused;
construct the actuator request; construct its deterministic intent; durably create
`request.json`; construct the receipt; durably create `publication-receipt.json` **last**.
The receipt is the publication marker. Filesystem-wide atomicity is not claimed. A bare
request after failure is unpublished, incomplete custody; same-ID automatic retry,
cleanup, and overwrite are forbidden. Separately governed recovery may be designed.

The read-only `load_published_production_chat_resource_provisioning_request` consumer
requires both fixed objects and verifies canonical request and receipt bytes, their
digests, deterministic intent digest, five exact decoded-artifact hashes, semantic
identities/digests, installation identity, P, canonical historical `verified_at`, and
the registered authority-definition digest before returning the original stored request
bytes. It uses only authenticated installation-state reads. It neither acquires publisher
authority nor writes, locks, deletes, publishes, executes, allocates, creates a final
bundle, performs current execution-time policy admission, or integrates with startup.
The historical/general arbitrary-request-file actuator remains a separate surface.

## Frozen candidate and current canonical authority definition

- capability: `production_chat_resource_provisioning_request_publish`
- subsystem: `causal_resource_principal_architecture`
- principal: `deterministic_production_chat_resource_provisioning_request_publisher`
- effects: `create_only_installation_state_resource_provisioning_request`; `finalize_production_resource_provisioning_request`; `read_exact_preexisting_causal_resource_principal_artifacts`; `read_exact_resource_trust_currentness_artifacts`; `read_governed_local_model_resource_policy`
- required phrases: `create-only production chat resource provisioning request`; `exact pre-existing provisioning input custody`; `digest-bound operator request publication`; `no allocation issuance`
- forbidden phrases: `resource allocation issuance`; `production provisioning bundle creation`; `ordinary startup publication`; `automatic request renewal`; `root principal minting`; `issuer provenance signing`; `private signing key custody`; `trust administration`; `currentness administration`; `policy administration`; `overwrite existing provisioning request`; `arbitrary filesystem mutation`; `model inference`; `grant local model inference`; `network egress`; `host scheduling`
- approvals: `independent operator approval evidence`; `exact definition digest binding`; `exact installation and provisioning identity binding`; `exact pre-existing principal provenance trust and currentness inputs`; `exact resource policy requested bounds and validity binding`; `create-only actuator-compatible request publication`
- purpose: `Permit only a deterministic production-chat resource-provisioning request publisher to verify one pre-existing canonical principal, provenance, trust, currentness, and policy bundle; bind exact requested resource bounds and validity for one existing installation and provisioning identity; and publish one immutable actuator-compatible request packet into fixed installation-state custody, while granting no allocation issuance, provisioning-bundle creation, root issuance, provenance signing, private-key custody, trust or currentness administration, policy administration, model inference or effect authority, arbitrary filesystem mutation, overwrite, renewal, or startup automation.`

Repository-native `authority_definition_digest(...)` yields
`349058b7e6959c06bfae1a8acabd01c6c022245c6fd404e63535cac6ed608cf5`.
The existing bundle-create definition remains unchanged at
`132f93c32f5490877a4748c0054dfb66aacb9f2a94ce560d69a0e65337c800f5`.

## Historical registrar handoff, current approval, non-effects, and next slice

The frozen artifact records the now-completed registration task as exactly
`register-production-chat-resource-provisioning-request-publish-authority-definition`.
Its registrar payload has exactly `task_classification`, `task_name`, `definitions`,
`operator_approval`, `requested_capability_id`, `authority_principal`,
`requested_effects`, `runtime_mutations`, and `changed_paths`. Classification is
`authority_definition_registration`; the four runtime-request values are `""`, `""`,
`[]`, and `[]`. Changed paths are only
`sentientos/codex_task_authority_admission.py`,
`tests/test_authority_definition_registration.py`, and this document. That historical artifact intentionally retains its approval template placeholders. The
current canonical registration instead carries immutable repository-operator evidence
`approval:production_chat_resource_provisioning_request_publish:349058b7e695:001`,
identity label `repository_operator`, status `approved`, the exact capability, definition
digest, and task bindings above, and independently recomputed evidence digest
`f7eece98ae6cd5e75a738c1b664a53ca0194a01c2b45dab07e8089fa41a1b4bc`.

The exact definition is now present in canonical `AUTHORITY_DEFINITIONS`. Registration is
definition-only: registered definition != runtime publisher, runtime publication,
allocation issuance, runtime grant, or runtime admission. Copied-catalog registration
proves no capability grant, runtime authority, effect, or runtime mutation and creates no
request, receipt, lock, final provisioning bundle, allocation, root issuance, or
provenance signature. The frozen machine artifact remains unchanged and truthfully
records its historical candidate-only posture.

The frozen machine artifact remains unchanged: its `runtime_consumer: not implemented`
and `published_request_consumer.implemented: false` fields truthfully record historical
design status, just as its candidate-only authority and unimplemented-publisher fields do.
Current repository implementation status is established by code and contract tests, not
by rewriting that historical normative artifact.

The one selected next slice is: **add a bounded operator-facing fixed-custody actuator
path that selects an existing installation + provisioning ID, loads the request only
through `load_published_production_chat_resource_provisioning_request(...)`, prepares the
exact intent for operator confirmation, and keeps execution as a separately explicit
confirmed action.** Publication and read-only custody verification remain distinct from
allocation-bearing bundle creation, execution, and startup integration.
