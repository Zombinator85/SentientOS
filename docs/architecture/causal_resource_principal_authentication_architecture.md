# Authenticated causal root issuer provenance and key custody

## Posture and inspected base

This is a **design-only, non-runtime, non-authority contract**. It implements no signing, key access, root minting, verification, allocation, GenesisForge composition, or control-plane status. The inspected clean repository SHA is `6e07a74b4814f656aa211bfcabb90c15dc13698d`.

The machine-readable normative companion is [`architecture/causal_resource_principal_authentication_architecture.json`](../../architecture/causal_resource_principal_authentication_architecture.json). Where this narrative abbreviates a closed decision, that contract controls.

## Current system and trust gap

`CausalResourcePrincipal` v1 is inert immutable evidence. Its verifier checks the exact schema, deterministic IDs, root relationship, sponsor and subject digests, epoch, canonical UTC validity, issuer syntax or an expected issuer string, predecessor, and binding digest. These are canonical self-consistency and expected-value checks. They do **not** prove that a trusted issuer emitted serialized evidence: a schema-aware party can manufacture a self-consistent mapping with an arbitrary syntactically valid `issuer_id`.

At the producer boundary, `RootPrincipalIssuer` invokes an injected `OperatorSponsorshipVerifier`, requires a `VerifiedOperatorSponsorship`, and then deterministically mints the root. The later `CausalResourcePrincipalVerifier` does not re-authenticate that producer or sponsorship verifier. Thus operator sponsorship verification, principal self-binding, and issuer authentication are three separate claims.

GenesisForge can explicitly carry an existing principal into the proof-budget request. The control plane revalidates it and reports `canonical_root_binding_verified` as observation-only attribution. It does not change proof-budget policy, admission, entitlement, or authority. That weaker status remains useful and must retain this exact meaning.

## Existing authentication, signing, and custody audit

| Mechanism | Classification / reuse decision | Finding |
|---|---|---|
| `SshStrategicSigner` | artifact signing / `requires_refactor_before_reuse` | Uses `ssh-keygen -Y sign` and `verify`, a namespace, subprocesses and temporary files; private custody is a configured key path and verification uses an allowed-signers file. Its environment configuration and hash-linked strategic artifact chain are not a persistent purpose-scoped runtime issuer boundary. Direct reuse would couple unrelated operational semantics. |
| `HmacTestStrategicSigner` | test-only authentication / `test_only` | Source and documentation label it `hmac-test`. A verifier holding the shared secret can mint signatures, so it is never production asymmetric issuer authentication. |
| operator report attestation | self-binding/integrity only / `incompatible_semantics` | Sealed report evidence does not establish a separately custodied asymmetric issuer. |
| common attestation helpers | self-binding/integrity only / `reuse_pattern_only` | Canonical JSON and sealing patterns are useful, but a digest is not authentication. |
| repository-local `nacl/signing.py` | compatibility stub / `must_not_use` | It calculates SHA-256 over message followed by key and exposes identical bytes as signing and verification keys. It is not Ed25519 and **MUST NOT be used as the security basis for causal-resource-principal issuer authentication**. |
| legacy `keyring_backend.py` | credential custody / `incompatible_semantics` | A generic facade is not a purpose-scoped signing authority. |
| external-model OS-keyring custody | credential custody / `reuse_pattern_only` | Its exact, operator-provisioned, read-only, fail-closed lookup; no admin surface; opaque reference; short exposure; secret erasure; and redacted errors are valuable patterns. An issuer key is not an external-model credential and must use a dedicated namespace and boundary. |

Core dependencies are deliberately empty. `cryptography>=42,<43` and `keyring>=24,<25` are in the `runtime` optional extra (and the aggregate `full` group), not core or test/dev. Consequently core evidence types must remain dependency-injected and unavailable by default; a production cryptographic backend may require the explicit runtime extra rather than silently expanding core.

## Alternatives and decision

1. **Put signature fields in principal v2 — reject.** Key rotation and re-signing would needlessly couple authentication evidence to causal identity and disrupt v1 consumers.
2. **Keep v1 and add a separate envelope — adopt.** This preserves stable transparent identity, durable audit evidence, and replaceable authentication.
3. **Replace the principal with a signed opaque token — reject.** This loses transparent deterministic bindings and auditability.
4. **Rely on trusted in-process object custody — reject.** It cannot authenticate serialized evidence after restart or transport.
5. **Use strategic SSH signing directly — reject.** It imports subprocess, temporary-file, configured-key-path, allowed-signers, and strategic artifact-chain concerns.
6. **Use injected Ed25519 signing and verification with separate custody — adopt.** It supplies independent verification without giving consumers signing power. The injection boundary contains the optional dependency and prevents a generic signing service.

The chosen design leaves `sentientos.causal_resource_principal:v1` unchanged and adds a durable immutable `RootPrincipalIssuerProvenance` claim for one exact root. Re-signing or rotation produces different provenance evidence for the **same** `principal_id`; authentication is not causal identity.

## Envelope and exact signed payload

The minimal envelope fields are `schema`, `principal_id`, `principal_binding_digest`, `issuer_id`, `signing_key_id`, `algorithm`, `signed_at`, `signature`, and `provenance_digest`. It deliberately does not duplicate sponsorship, subject, epoch, or validity fields: the signed binding digest commits to the exact canonical principal containing them. Verification nevertheless checks the explicit envelope `issuer_id` against the principal and trusted catalog.

The signed payload is the exact mapping containing:

```text
schema, domain, principal_id, principal_binding_digest,
issuer_id, signing_key_id, algorithm, signed_at
```

Its canonical bytes are UTF-8 JSON with sorted keys, compact `,`/`:` separators, `ensure_ascii=false`, and exactly one trailing LF. Dataclass representations, insertion order, and free-form text are forbidden. The fixed domain is:

```text
sentientos.causal_resource_principal.issuer_provenance:v1
```

This binds principal, issuer, key, algorithm, time, schema, and purpose, preventing substitution, algorithm confusion, and cross-protocol signature reuse.

## Algorithm and identity policy

Production uses Ed25519 from `cryptography.hazmat.primitives.asymmetric.ed25519`, available only through an injected runtime-extra backend. The private form is the 32-byte raw seed held only in secret custody. The trusted catalog stores the 32-byte raw public key as unpadded base64url. The envelope stores the 64-byte signature as unpadded base64url. `signing_key_id` is `ed25519-sha256:` plus 64 lowercase hex characters computed over the raw public key. Unsupported algorithms, malformed encodings, unavailable crypto, or backend errors fail closed without negotiation or fallback.

`issuer_id` remains the stable logical issuer and uses the existing issuer grammar, but its string alone is never trusted. `signing_key_id` identifies one issuer-controlled key generation by canonical fingerprint; it changes on rotation. A display label is insufficient. The resource-principal `epoch` is neither a key generation nor a trust epoch.

## Signer, verifier, and custody separation

The purpose-scoped signer exposes only a semantic operation such as `authenticate_root_provenance(principal)`. It internally validates the exact root and constructs the fixed payload. An arbitrary caller-visible `sign(bytes)` is forbidden because it turns the signer into a confused deputy. The signer is owned by an operator-configured root-producing process, cannot allocate resources, admit work, manage keys, mutate trust, or grant effects.

The receiver has a `RootIssuerTrustStore` and `RootIssuerProvenanceVerifier`, containing public material only. It cannot sign or mutate trust. Verification capability is not signing capability; a key reference is not signing authority.

Private material belongs behind an injected external signer or dedicated operator-provisioned keystore. A dedicated OS-keyring namespace is a plausible first backend, following the governed credential pattern, but is not selected blindly and must not reuse external-model credentials. Requirements are exact scoped reference, read/use only, no ordinary-runtime creation/admin/export, shortest feasible exposure, fixed redacted errors, no repository/environment/evidence storage, and fail-closed unavailability. A signer compromise can authenticate false roots, so operational containment and revocation remain necessary; even then it cannot directly allocate resources.

Trusted public keys live in a separately operator-provisioned, digest-sealed, versioned catalog keyed by `(issuer_id, signing_key_id, algorithm)`, with public key, validity bounds, and revocation status. Runtime callers cannot add entries. Trust mutation is a separate operator-controlled operation. A public key in an envelope is forbidden and never a trust input. A valid mathematical signature under an attacker key is not a trusted issuer.

## Rotation, revocation, durability, and replay

Rotation creates a new fingerprint and new envelope while leaving `principal_id` unchanged. Explicit old/new overlap is bounded by catalog validity. Durable verification uses a retained, sealed historical trust entry applicable at `signed_at`, plus current revocation policy; current trust state may invalidate earlier evidence. Rotation machinery is not implemented here.

Key revocation, issuer distrust, single-principal revocation, natural principal expiry, and future allocation revocation are distinct operations. Entitlement-bearing use requires current issuer/key revocation checks and a defined principal-revocation policy. Key revocation must not masquerade as allocation revocation.

Principal plus envelope are durable immutable claim evidence and may be stored together; no private material accompanies them. Signatures survive restart only when the relevant historical trust snapshot and current revocation policy validate. Storage is deferred.

Replay of the same envelope is allowed while principal and trust state are current. Identity provenance is not a nonce, consumable, or one-shot effect token. Future allocation and effect layers own their own anti-replay rules.

## Producer and consumer flows

Producer:

```text
sponsorship evidence -> OperatorSponsorshipVerifier
 -> VerifiedOperatorSponsorship -> RootPrincipalIssuer
 -> CausalResourcePrincipal -> purpose-scoped provenance signer
 -> RootPrincipalIssuerProvenance
```

The signature links the already-bound sponsorship digest but does not re-perform or prove the correctness of human/operator sponsorship authentication.

Consumer:

```text
principal + envelope (serialized claims)
 -> canonical principal validation
 -> exact envelope schema/digest and principal binding
 -> trusted issuer/key catalog lookup
 -> algorithm/signature and key validity/revocation checks
 -> principal time/revocation checks
 -> process-local AuthenticatedRootPrincipalEvidence
```

The verified result is constructed only inside the verifier and is not accepted from serialized caller input. A caller can serialize claims, but `verified=true` or a caller-created wrapper never establishes verification.

GenesisForge should eventually carry principal and provenance as separate untrusted claims. Verification occurs at the receiving control boundary, which may then construct a process-local typed bundle; a class name alone is not custody. Runtime changes are explicitly deferred.

The existing `canonical_root_binding_verified` remains self-consistency-only. A future `authenticated_root_issuer_provenance_verified` status is truthful only after canonical validation, exact binding, trusted catalog lookup, signature verification, and currentness checks all succeed.

## Authority and resource-allocation boundary

The non-collapse rules are absolute:

- canonical principal is not authenticated provenance;
- issuer authentication is not operator sponsorship verification;
- authenticated provenance is not `ResourceAllocation`, effect authority, admission, or operator approval;
- signing-key possession is not allocator authority;
- a trusted issuer is not an unlimited resource sponsor.

A future `ResourceAllocation` may reference a root only after both canonical evidence and authenticated issuer provenance have been verified under current trusted issuer/key custody, including applicable revocation checks. This prerequisite creates no allocation: separate allocator policy, admission, limits, and authority remain mandatory. Observation-only attribution may explicitly degrade to canonical-only evidence; entitlement-bearing consumers must fail closed.

Missing or malformed provenance, unknown issuer/key, unsupported algorithm, signature or binding mismatch, revoked/not-yet-valid/expired key, stale/corrupt trust catalog, or unavailable crypto all prevent authenticated status. Observation-only code may report the weaker canonical status, never silently upgrade it.

## Threat model

| Threat | Architectural mitigation |
|---|---|
| Manufactured self-consistent unsigned principal | Authenticated consumers require the separate trusted-key envelope. |
| Attacker signs with own key or substitutes a public key | Only the operator catalog supplies keys; envelope keys are forbidden. |
| Issuer, key ID, algorithm, or principal substitution | Every value is signed, catalog-bound, and cross-checked. |
| Cross-protocol reuse | Fixed signed schema and domain separate the protocol. |
| Verifier can mint | Ed25519 public verification and separate interfaces/custody. |
| Signer signs arbitrary attacker bytes | Semantic purpose-specific API builds canonical bytes internally. |
| Arbitrary keyring lookup | Exact configured reference and dedicated namespace only. |
| Secret leakage | No secret serialization/export/repr; fixed redacted errors and short exposure. |
| Stale revoked key | Versioned trust catalog plus current revocation checks. |
| Rotation changes causal identity | Separate envelope preserves v1 identity. |
| Authentication mistaken for entitlement/effects | Verified result has no grants; allocator and admission remain separate. |
| Compromised signer mints roots | Purpose scope, containment, rotation/revocation; no allocation follows automatically. |
| Signature mistaken for sponsorship proof | It binds the sponsorship digest but does not rerun sponsorship verification. |
| Test HMAC enabled in production | Closed production algorithm policy rejects `hmac-test`. |
| Compatibility NaCl treated as Ed25519 | Explicit `must_not_use` decision and `cryptography` backend constraint. |
| Crypto unavailable causes fallback | Fail closed; only an explicitly labeled canonical-only observation may remain. |

## What not to build

Do not build custom cryptography, use repository-local fake NaCl as production security, use production HMAC for independent verification, accept caller keys, store private keys in the repository/principal/envelope/environment, treat signatures or roots as authority/allocation, expose a universal arbitrary-byte signing service, bundle key generation/admin with issuance, silently fall back when crypto is unavailable, or automatically allocate resources after authentication.

## Smallest next implementation slice

Implement **one bounded slice**: the immutable `RootPrincipalIssuerProvenance` claim, canonical payload builder, purpose-scoped signer/verifier protocols, verifier-owned process-local result, and deterministic test-only backend. Keep production signing and key custody unavailable, and do not integrate the producer, GenesisForge, control plane, storage, rotation/revocation, or resource allocation.

## Unresolved questions

1. Which dedicated production keystore/backend and deployment platforms are admitted?
2. What operator-controlled trust-catalog mutation and historical snapshot format is canonical?
3. What principal-specific revocation registry must exist before entitlement-bearing use?
