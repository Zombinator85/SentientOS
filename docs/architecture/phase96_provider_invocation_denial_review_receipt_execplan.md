# Phase 96 Provider Invocation Denial Review Receipt Execplan

## Goal

Phase 96 adds a deterministic, metadata-only `ProviderInvocationDenialReviewReceipt` for Phase 95 `ProviderInvocationReadinessManifest` and `ProviderInvocationReadinessPreflight` objects. The receipt lets an operator or auditor affirm, reject, expire, or constrain the Phase 95 denial posture while preserving the invariant that provider invocation is still forbidden.

## Non-goals

Phase 96 does not call providers, send prompt text, import provider SDKs, open sockets, perform HTTP, resolve DNS, read environment variables, read files, access config stores, access vaults/keychains/cloud secrets, create credentials, create endpoints, create clients, create sessions, create transports, create streams, build requests, perform semantic generation, retrieve or write memory, commit retention, execute tools/actions, route/admit/execute work, or orchestrate runtime behavior.

It does not modify `prompt_assembler.py`, live `assemble_prompt(...)`, memory runtime modules, truth runtime modules, embodiment runtime modules, action modules, retention modules, routing, admission, execution, or orchestration behavior.

## Dependency chain: Phase 61 through Phase 95

Phase 96 sits after the context-hygiene spine created by Phases 61-95: context packets and receipts, truth-gated selection, blocked-risk preservation, embodiment/privacy adapters, prompt preflight, safety metadata, source-kind safety contracts, prompt handoff, dry-run envelopes, constraint verification, adapter/compliance harnesses, shadow previews/blueprints, audit receipts, static guardrails, adversarial tests, policy decisions, operator review, synthetic/internal candidate and display contracts, model-call preflight/review contracts, provider dry-run, simulation, network-egress review, null transport, null-only registry, transport capability custody, credential custody, endpoint custody, client custody, and Phase 95 provider invocation readiness/preflight.

## Invocation-denial review is not invocation approval

The Phase 96 receipt can record review status, reviewer metadata, linked Phase 95 IDs/digests, accepted or rejected denial/gap/constraint codes, expiration state, forbidden override findings, no-runtime proof, and a deterministic digest. It cannot turn readiness into provider invocation approval.

## Review statuses and scopes

Statuses are compact deterministic values: accepted, accepted-with-conditions, rejected, expired, invalid, forbidden-invocation-override-attempted, and not-applicable.

Scopes are metadata-only. `invocation_denial_review_gate` can be accepted for clean linked Phase 95 evidence. `future_external_security_review_gate` and `future_invocation_denial_audit_gate` can be accepted only with conditions and only while all provider/runtime allowances remain false. Actual provider invocation, provider send, network egress, credential use, endpoint use, provider-client use, provider-SDK use, tool/action use, and external user-visible use are forbidden scopes that produce denial or forbidden override findings when approval is attempted.

## Denial and gap acceptance behavior

The receipt derives stable review codes from Phase 95 readiness gaps, missing evidence, findings, constraints, digest-chain completeness, provider-invocation-forbidden markers, metadata-only-not-invocable markers, null-only metadata status, and denial/forbidden preflight statuses. Text-only findings and gaps are normalized into deterministic codes. Satisfaction requires required denial and constraint codes to be accepted/approved, required gap codes to be accepted when present, and no required code to be rejected.

## Forbidden invocation override rules

A review is invalid or forbidden-override-attempted if it tries to approve actual provider invocation, provider send, network egress, credential use, endpoint use, client use, provider SDK use, DNS/HTTP/socket use, semantic generation, tool calls, memory retrieval/write, retention, action execution, routing/admission/execution/orchestration, dirty Phase 91/92/93/94/95 evidence, digest mismatches, incomplete audit chains treated as approval-ready, or prompt/raw/runtime/provider marker findings.

## Future external security review gate behavior

The future external security review gate is only metadata. Approval records that a future external review packet may be prepared; it does not authorize provider invocation, provider send, credentials, endpoints, clients, provider SDKs, network access, semantic generation, memory, tools, retention, actions, routing, admission, execution, fulfillment, or orchestration.

## Digest behavior

The review digest is deterministic over stable metadata-safe fields. It changes when linked readiness/preflight digests, reviewer reference, decision, review scope, accepted/rejected code sets, expiration, status, findings, warnings, constraints, or allowance flags change. It excludes prompt text, raw payloads, credentials, endpoints, provider handles, network handles, runtime handles, and nondeterministic timestamps unless supplied as stable metadata.

## Guardrail behavior

The static prompt-boundary guardrail scans the Phase 96 module by default. The module must remain free of provider SDK imports, network/HTTP/socket/DNS/config/secret access, prompt assembler imports, memory/action/retention/routing runtime imports, and runtime/provider calls. Phase 96 schema labels such as `provider_invocation_forbidden`, `metadata_only_not_invocable`, `provider_send_forbidden`, and `network_access_forbidden` are metadata labels only.

## Tests

The Phase 96 test suite covers clean receipt construction, status and scope behavior, future metadata gates, reject/expired/invalid states, digest/id mismatch failures, audit-chain incompleteness, forbidden scopes, forbidden allowance flags, dirty Phase 91-94 evidence, required code acceptance/rejection, helper predicates, digest determinism and mutation triggers, non-mutation of linked Phase 95 objects, static call/import purity, Phase 90-95 invariants, blocked/adversarial marker behavior, guardrail scanning, architecture boundaries, and import purity.

## Deferred work

A future phase may define an external security review packet or a formal provider-invocation denial attestation. Those future packets must remain separate from actual provider invocation unless a later explicitly reviewed contract changes the system posture. Phase 96 itself grants no runtime authority.
