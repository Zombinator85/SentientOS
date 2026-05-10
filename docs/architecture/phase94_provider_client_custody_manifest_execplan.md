# Phase 94 Provider Client Custody Manifest Exec Plan — No Clients

## Goal

Phase 94 adds a deterministic provider-client custody manifest and preflight contract for future provider transport review evidence. It declares what evidence would be needed for client, session, transport, stream, request-builder, and retry-executor custody while keeping the implementation metadata-only.

## Non-goals

Phase 94 does not accept, create, import, store, configure, validate, open, or use real provider clients, SDK clients, HTTP clients, sessions, transports, sockets, streams, request builders, retry policies, credentials, endpoints, provider invocations, model calls, tool calls, semantic outputs, memory access, retention, routing, admission, execution, or orchestration.

## Dependency Chain

Phase 94 depends on the context-hygiene spine from Phase 61 through Phase 93:

- Phase 61 through Phase 74 define packet, prompt handoff, dry-run, compliance, and audit receipt boundaries.
- Phase 75 and Phase 76 define static/adversarial prompt-boundary guardrails.
- Phase 77 through Phase 83 define policy, operator review, internal candidate/display, and model-call review contracts without provider invocation.
- Phase 84 through Phase 88 define non-sendable provider dry-run, simulation, network-egress preflight, and review evidence.
- Phase 89 and Phase 90 prove null transport and null-only transport registry behavior.
- Phase 91 keeps real transport capability and registration forbidden.
- Phase 92 keeps credential custody no-secret.
- Phase 93 keeps endpoint custody no-endpoint.

## Client custody manifest is not client custody

`ProviderClientCustodyManifest` is a declaration and denial artifact. A clean manifest reports `client_custody_no_clients`; forbidden client/session/transport evidence produces findings and non-clean statuses. The manifest carries deterministic digests and optional links to Phase 91 capability metadata, Phase 92 credential custody metadata, and Phase 93 endpoint custody/preflight metadata.

## No-client invariant

The clean path proves:

- no client material;
- no client references;
- no client instantiation;
- no provider SDK imports;
- no sessions, transports, streams, request builders, or retry executors;
- no credentials;
- no endpoints;
- no network, socket, HTTP, provider send, LLM call, semantic generation, memory, retention, action, routing, admission, execution, or orchestration authority.

## Future client contract placeholder

`client_custody_future_client_contract_placeholder` is metadata-only. It is not a factory, import path, class name, provider package name, session builder, executable call surface, endpoint surface, or credential surface.

## Real access remains forbidden

Provider SDK clients, HTTP clients, socket clients, provider-specific clients, sessions, transports, streaming clients, request builders, retry executors, endpoint values, credentials, auth headers, request/response handles, network handles, runtime handles, provider parameters, and model parameters are all denied or treated as findings.

## Preflight behavior

`ProviderClientCustodyPreflight` defaults to denial unless the manifest is clean no-client metadata, the requested custody kind is one of the allowed metadata-only kinds, all requested access flags are false, all no-client/no-network/no-runtime flags are true, and any linked Phase 91/92/93 artifacts remain null-only/no-secret/no-endpoint metadata.

A clean preflight can produce only `client_preflight_no_clients_allowed`, which means no-client metadata compatibility. It does not mutate capability manifests, credential manifests, endpoint manifests, endpoint preflights, registries, or transport state.

## Client detection behavior

Phase 94 performs conservative string-pattern detection over metadata keys and values. It denies likely provider client/session/transport/credential/endpoint/network material such as provider SDK names, `client=`, `session=`, `transport=`, HTTP client markers, socket/websocket markers, stream/retry/executor/request-builder markers, endpoint/base URL markers, credential markers, and URL markers. Explicit negative markers such as `client_instantiation_forbidden`, `provider_client_use_forbidden`, `does_not_create_clients`, and `no_client_material` are treated as metadata-only denials rather than client references.

## Digest behavior

Manifest and preflight digests are deterministic SHA-256 digests over stable fields with their own IDs and digest fields blanked. They change when custody kind, declared/forbidden properties, flags, linked digests, requested kinds, requested access flags, findings, constraints, gaps, warnings, or no-client/no-network/no-runtime markers change. They do not include real clients, endpoints, credentials, raw payloads, handles, provider/model parameters, prompt text, timestamps, or network artifacts.

## Guardrail behavior

The Phase 75 guardrail default scan includes `sentientos/context_hygiene/prompt_provider_client_custody.py`. The module is scanned as prompt-boundary code and remains free of provider SDK imports, HTTP/socket imports, DNS/config/secret/runtime imports, prompt assembler imports, model/provider calls, network calls, environment/config/vault/keychain/secret access, memory access, action/retention/routing calls, and client/session/transport construction.

## Tests

`tests/test_phase94_provider_client_custody_manifest.py` covers the clean no-client manifest/preflight path, forbidden custody kinds, provider SDK/HTTP/socket/session/transport/stream/retry/request-builder markers, requested access flags, linked Phase 91/92/93 gating, digest determinism/change behavior, no-mutation guarantees, null-only registry preservation, no-secret/no-endpoint preservation, Phase 63/62B metadata behavior, adversarial marker blocking, and guardrail scanning.

## Deferred work

Future work may add an explicit client custody review receipt or real transport client review. Such work must remain behind separate review gates and must not inherit runtime authority from Phase 94.
