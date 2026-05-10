# Phase 95: Provider Invocation Readiness Manifest — Still Forbidden

## Goal

Phase 95 adds a deterministic Provider Invocation Readiness Manifest and preflight contract. It aggregates the Phase 91 transport capability/registration evidence, Phase 92 credential custody evidence, Phase 93 endpoint custody evidence, and Phase 94 client custody evidence into one readiness artifact that answers a deliberately narrow question: **is real provider invocation ready?**

For Phase 95 the answer remains **no**. A complete clean chain can only prove `invocation_readiness_null_only_metadata` and `invocation_preflight_metadata_only_not_invocable`.

## Non-goals

Phase 95 does not call an LLM, send prompt text, import provider SDKs, make network calls, create clients/sessions/transports, create credential objects, create endpoint objects, open sockets, perform HTTP requests, resolve DNS, read environment variables, read files, access config stores, access vaults/keychains/cloud secrets, retrieve memory, write memory, commit retention, execute actions, route/admit/orchestrate work, or change live `assemble_prompt(...)` behavior.

## Dependency chain: Phase 61 through Phase 94

Phase 95 sits on the context-hygiene spine that began with Phase 61 `ContextPacket` contracts and continued through truth-gated selection, blocked-risk preservation, embodiment/privacy eligibility, prompt preflight, safety/source-kind contracts, handoff manifests, dry-run envelopes, constraint verification, adapter/compliance harnesses, shadow previews/blueprints, materialization audit/policy/operator review, synthetic/internal/no-LLM prompt candidates, display receipts, model-call preflight/review denial, provider dry-run/review/simulation, network-egress preflight/review, null transport receipts, null-only transport registry, provider transport capability, credential custody, endpoint custody, and client custody.

The Phase 95 manifest consumes only metadata IDs, statuses, flags, findings, gaps, constraints, and stable digests from that chain.

## Invocation readiness is not invocation

Readiness is a declaration, not an execution path. It has no provider-call authority, no network-egress authority, no credential-use authority, no endpoint-use authority, no client-use authority, no semantic-generation authority, no memory authority, and no tool/action authority.

## Aggregate custody/readiness model

A clean readiness manifest requires:

- Phase 91 null-only transport capability evidence.
- Phase 91 null-only registration preflight evidence.
- Phase 92 no-secret credential custody manifest and preflight evidence.
- Phase 93 no-endpoint custody manifest and preflight evidence.
- Phase 94 no-client custody manifest and preflight evidence.
- Optional Phase 90 registry evidence, if provided, to remain null-only.
- Optional Phase 89 null transport receipt evidence, if provided, to remain no-send/no-network/no-runtime.

## Forbidden invocation invariant

All readiness and preflight outputs keep invocation, provider send, credentials, endpoints, clients, network, sockets, HTTP, DNS, provider SDKs, semantic generation, tools, memory, retention, actions, routing, admission, and runtime authority disabled. A clean chain is still metadata-only and not invocable.

## Missing evidence behavior

If any required Phase 91 through Phase 94 artifact is absent, the readiness status becomes `invocation_readiness_missing_evidence`, the missing evidence key is listed, the digest chain is incomplete, and preflight cannot produce the clean metadata-only-not-invocable status.

## Preflight behavior

The preflight contract always denies real invocation. It returns `invocation_preflight_metadata_only_not_invocable` only for a clean null-only metadata manifest with complete digest chain, no requested invocation/provider-send/network/access flags, and all no-runtime/no-network markers true. Any requested invocation, provider send, network access, credential access, endpoint access, client access, provider SDK access, DNS, HTTP, socket, semantic generation, registration, or disabled no-* marker causes denial or a specific detected status.

## Detection behavior

Phase 95 conservatively classifies dirty linked metadata and explicit marker evidence as credential, endpoint, client, network/provider-send, or runtime-authority findings. Explicit negative schema labels such as forbidden, no-*, does_not_*, and metadata_only_not_invocable remain allowed as evidence of denial rather than authority.

## Digest chain behavior

The readiness digest is deterministic over stable manifest fields and linked digests. The preflight digest is deterministic over stable preflight fields, the readiness digest, requested flags, no-* markers, findings, warnings, gaps, constraints, and digest-chain completeness. Digests intentionally exclude prompt text, raw payloads, credentials, endpoint values, provider handles, network handles, runtime handles, provider/model parameters, and nondeterministic timestamps.

## Guardrail behavior

The Phase 75 prompt-boundary guardrail scans the new module by default. The module remains pure metadata code and must not import provider SDKs, network clients, socket/DNS/config/secret access modules, prompt assembler code, memory modules, action/retention/routing/admission/runtime modules, or call provider/network/runtime functions.

## Tests

Phase 95 tests cover clean chain behavior, missing evidence, dirty Phase 91/92/93/94 evidence, requested invocation/access denial, no-* marker enforcement, marker evidence blocking, helper predicates, digest determinism and sensitivity, no mutation, Phase 90 through Phase 94 preservation, blocked candidate non-enablement, embodiment metadata compatibility, guardrail coverage, and import-purity compatibility.

## Deferred work

Future work may add an explicit invocation-denial review or external security review. Such future work must remain a new explicit phase and cannot treat Phase 95 as provider invocation approval.
