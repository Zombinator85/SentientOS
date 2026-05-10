# Phase 99: Formal Provider Invocation Denial Attestation — Metadata Only

## Goal

Phase 99 adds a deterministic formal provider invocation denial attestation that binds the Phase 95 invocation readiness manifest, Phase 96 invocation-denial review receipt, Phase 97 external security review packet, and Phase 98 external audit export receipt into one metadata-only roll-up statement. The artifact attests that provider invocation remains forbidden.

## Non-goals

- It is not provider invocation approval.
- It is not provider submission.
- It is not export I/O or external delivery.
- It does not contain packet bodies, artifact bodies, prompt text, internal candidate text, synthetic prompt text, dry-run prompt text, hidden chain-of-thought, raw payloads, secrets, endpoints, clients, network handles, runtime handles, provider/model parameters, tool schemas, or destination material.
- It does not import provider SDKs, create clients/sessions/transports, read environment variables, access files/config stores/vaults/keychains/cloud secrets, resolve DNS, open sockets, make HTTP requests, retrieve/write memory, execute actions, route/admit work, or modify live `assemble_prompt(...)` behavior.

## Dependency chain

Phase 99 depends on the context-hygiene spine from Phase 61 through Phase 98:

1. Phase 61 created context packets and receipts.
2. Phase 62 and 62B added truth-gated selection and blocked-risk preservation.
3. Phase 63 through Phase 74 added eligibility adapters, preflight, handoff, dry-run, verifier, adapter, compliance, blueprint, and audit receipt contracts.
4. Phase 75 and Phase 76 added static guardrails and adversarial failure-mode tests.
5. Phase 77 through Phase 88 added policy, operator review, internal candidate/display/model-call reviews, provider dry-run/simulation, and network-egress reviews while provider invocation remained forbidden.
6. Phase 89 through Phase 94 established null transport only, transport capability, no-secret credentials, no-endpoint endpoint custody, and no-client client custody.
7. Phase 95 added invocation readiness metadata while keeping invocation forbidden.
8. Phase 96 affirmed invocation denial for future metadata review gates only.
9. Phase 97 produced a metadata-only external security review packet.
10. Phase 98 produced a metadata-only external audit export receipt without export I/O.

## Formal denial attestation is not invocation approval

The attestation can only record denial-oriented decisions: `attest_provider_invocation_forbidden`, `attest_metadata_only_not_invocable`, or `attest_with_conditions`. Rejection, more-evidence, more-redaction, missing-evidence, invalid, expired, sensitive-material, runtime-authority, override, and export-not-ready states remain non-ready and non-invocable.

## Formal denial attestation is not export I/O

The attestation stores digest links and metadata flags only. It cannot perform external delivery, upload, email, webhook calls, file writes, object storage writes, network I/O, provider sends, or live transport activity.

## Allowed and forbidden scopes

Allowed metadata-only scopes:

- `provider_invocation_denial_attestation`
- `external_audit_denial_attestation`
- `internal_security_denial_attestation`
- `invocation_denial_chain_attestation`

Forbidden scopes:

- `provider_invocation_approval_forbidden`
- `provider_submission_forbidden`
- `network_egress_forbidden`
- `export_delivery_forbidden`
- `tool_or_action_forbidden`
- `external_user_visible_forbidden`

Forbidden scopes fail closed and cannot produce a ready attestation.

## Evidence summary behavior

The evidence summary aggregates counts and booleans only: linked artifact count, Phase 98 readiness, optional Phase 97 readiness, optional Phase 96 denial affirmation, optional Phase 95 metadata-only denial posture, digest-chain completeness, constraint count, warning count, and finding count. It never embeds artifact bodies or packet bodies.

## Sensitive material fail-closed rules

The builder and validator fail closed on prompt markers, hidden-reasoning markers, secrets or secret references, endpoint material, client material, network/runtime handles, provider/model parameters, tool schemas, raw payload markers, invocation approval markers, export destination markers, provider invocation markers, and runtime/tool/action/routing/retention/memory markers unless they appear in explicit negative metadata markers.

## No-export/no-invocation invariant

A ready attestation requires Phase 98 to be ready or ready with conditions, metadata-only, non-exporting, and preserving invocation denial. It also requires all attestation-level export, delivery, sensitive-material, runtime-authority, and allowance flags to remain false.

## Digest behavior

The attestation digest is deterministic over stable metadata-safe fields. It changes when linked digests, expected export digest, attestor reference, label, scope, decision, accepted/rejected codes, evidence summary, expiration metadata, findings/warnings/constraints, allowance flags, export I/O flags, or no-sensitive/no-runtime markers change. It excludes packet bodies, artifact bodies, prompt text, raw payloads, credentials, endpoints, handles, runtime material, provider/model parameters, tool schemas, destination material, and nondeterministic timestamps unless explicitly supplied as stable metadata.

## Guardrail behavior

The Phase 75 guardrail script scans the new module by default. The module is expected to remain free of provider/network/socket/HTTP/DNS/config/secret/client/session/transport/export/prompt/runtime violations and does not require prompt-text allowlisting.

## Tests

Phase 99 tests cover clean construction, all allowed scopes, decision status mapping, missing/expired/digest-mismatch/missing-evidence blocks, Phase 98 gating blocks, forbidden scopes, export/sensitive/runtime/allowance flags, adversarial metadata markers, evidence summary shape, boolean helpers, digest determinism and changes, input immutability, forbidden-call static checks, prior-phase invariant preservation, embodiment-metadata paths, blocked attempted-candidate behavior, and guardrail scanning.

## Deferred work

Any future Phase 100 consolidation, release-blocker summary, or public-surface audit summary must continue to consume Phase 99 as metadata-only denial evidence and must not treat it as provider invocation approval or export delivery authority.
