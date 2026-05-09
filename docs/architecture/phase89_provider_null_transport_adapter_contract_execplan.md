# Phase 89: Provider Null Transport Adapter Contract — No Network

## Goal

Phase 89 adds a deterministic, metadata-only provider null transport adapter receipt for Phase 84 `ProviderDryRunRequestEnvelope` artifacts after a Phase 87 network-egress preflight and a Phase 88 review receipt approve `future_transport_null_adapter_gate`.

The artifact proves that no transport was attempted. Null transport is not network transport.

## Non-goals

Phase 89 does not call an LLM, send prompt text to a model or provider, import provider SDKs, make network calls, create endpoint/client/session/credential objects, open sockets, perform HTTP requests, retrieve or write memory, commit retention, execute tools/actions, route/admit/fulfill/orchestrate work, or perform semantic generation. It does not modify `prompt_assembler.py` and does not change live `assemble_prompt(...)` behavior.

## Dependency chain: Phase 61 through Phase 88

Phase 89 depends on the established context-hygiene spine:

1. Phase 61 introduced `ContextPacket` contracts and receipts.
2. Phase 62 and 62B added truth-gated context selection and blocked-risk preservation.
3. Phase 63 added embodiment/privacy eligibility adapters.
4. Phase 64 through Phase 76 built prompt preflight, source safety, handoff, dry-run, verifier, adapter, compliance, shadow, audit, static guardrail, and adversarial coverage.
5. Phase 77 through Phase 83 added policy, operator review, synthetic/internal candidate, display, model-call preflight, and model-call review metadata gates.
6. Phase 84 produced non-sendable provider dry-run envelopes.
7. Phase 85 reviewed dry-run egress while preserving no-send constraints.
8. Phase 86 produced a fixed-stub provider simulation result with no network and no semantic generation.
9. Phase 87 assembled a network-egress preflight while still forbidding egress.
10. Phase 88 added a provider network-egress review receipt that may approve future metadata gates, including `future_transport_null_adapter_gate`.

## Null transport is not network transport

The Phase 89 receipt is a no-op/digest/audit metadata adapter only. It records IDs, digests, statuses, findings, warnings, constraints, and explicit absence markers. It does not create an endpoint URL, API key, auth header, provider client, network session, HTTP request, socket, request handle, response handle, provider invocation, semantic output, model output, tool call, or runtime side effect.

## Statuses, modes, and scopes

Statuses are compact and deterministic: ready, ready-with-warnings, blocked/invalid input, review missing/not satisfied, preflight/dry-run not ready, network forbidden, credentials detected, endpoint detected, client detected, runtime authority detected, and send attempt detected.

Allowed modes are metadata-only:

- `null_transport_mode_noop`
- `null_transport_mode_digest_only`
- `null_transport_mode_audit_only`

Unknown, live-network, provider-send, HTTP-request, socket-transport, and semantic-generation modes are forbidden.

Allowed scopes are:

- `future_transport_null_adapter_gate`
- `internal_null_transport_audit`

Provider-send, network-egress, credential-use, endpoint-use, provider-client-use, and external-user-visible scopes are treated as forbidden override attempts.

## Audit chain behavior

The receipt builds a deterministic `ProviderNullTransportAuditChain` over:

- dry-run ID/digest;
- network preflight ID/digest;
- network review receipt ID/digest;
- Phase 87 egress-review and simulation linkage when available;
- candidate ID/digest;
- packet ID/scope.

`digest_chain_complete` is true only when required Phase 84, Phase 87, and Phase 88 IDs and digests are present and matching. Expected digest arguments may be supplied to assert linkage; mismatches produce deterministic findings instead of invented evidence.

## Null-send proof

The receipt records `sent=False`, `bytes_sent=0`, `request_created=False`, `response_received=False`, and all network/provider/socket/HTTP/runtime attempt markers as false for clean receipts. `provider_null_transport_sent_nothing(...)` returns true only for ready receipts that preserve those no-send and no-network markers.

## Gating rules

The builder blocks unless the dry run is ready or ready-with-warnings and non-sendable, the network preflight is ready/review-required and still provider/network-forbidden, the Phase 88 review satisfies that preflight, the Phase 88 review approves `future_transport_null_adapter_gate`, the mode and scope are allowed, the digest chain is complete, and every no-network/no-provider/no-runtime proof flag remains true.

Any send attempt, nonzero byte count, request/response creation, credential use, endpoint use, provider-client use, socket open, HTTP attempt, LLM attempt, semantic-generation attempt, tool/memory/retention/action/routing attempt, raw payload marker, runtime handle marker, or provider/model parameter marker blocks the receipt.

## Digest behavior

`compute_provider_null_transport_digest(...)` hashes stable metadata-safe fields only. The digest changes when dry-run, preflight, review, mode, scope, audit chain, findings, warnings, constraints, send/byte/request/response attempt fields, or no-runtime/no-network markers change. It excludes prompt text, raw payloads, credentials, endpoints, provider handles, network handles, runtime handles, provider/model parameters, and nondeterministic timestamps.

## Guardrail behavior

`verify_context_hygiene_prompt_boundaries.py` includes `sentientos/context_hygiene/prompt_provider_null_transport.py` in default scans. The module remains subject to provider SDK, web/network client, prompt assembler, memory, action, retention, routing, socket/HTTP live-use, provider/model call, network call, memory/action/retention/routing, and tool-code guardrails. Negative marker names such as `socket_opened=False` and `http_request_attempted=False` are treated as metadata proof fields, not live transport allowance.

## Tests

Phase 89 tests cover ready and warning paths, missing/expired/mismatched reviews, dry-run and preflight denials, missing null-adapter approval, forbidden modes/scopes, digest-chain incompleteness and mismatch, every send/network/provider/runtime attempt marker, no-network/no-runtime proof flags, helper strictness, digest determinism and change sensitivity, input immutability, import purity, Phase 63→84→87→88→89 chaining, blocked attempted-candidate propagation, adversarial marker blocking, and guardrail inclusion.

## Deferred work

Future phases may define additional review metadata or real network-egress contracts. Phase 89 intentionally does not implement those paths; it is a prerequisite proof artifact that preserves the transport boundary while sending nothing.
