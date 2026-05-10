# Phase 93 Provider Endpoint Custody Manifest — No Endpoints

## Goal

Phase 93 adds a deterministic Provider Endpoint Custody Manifest and endpoint custody preflight contract. The artifact defines the evidence a future real provider transport would need for endpoint custody without accepting, storing, resolving, validating, dialing, pinging, probing, or using any real endpoint.

## Non-goals

Phase 93 does not contain endpoint URLs, hostnames, IP addresses, ports, DNS results, provider clients, network sessions, HTTP clients, sockets, auth headers, credentials, request/response handles, provider invocations, semantic outputs, model outputs, tool calls, or runtime side effects. It does not read environment variables, endpoint files, config stores, keychains, vaults, cloud secret managers, or OS credential/config APIs. It does not call an LLM, send prompt text, import provider SDKs, make network calls, open sockets, perform HTTP requests, retrieve/write memory, commit retention, execute tools/actions, or route/admit/orchestrate work.

## Dependency chain

Phase 93 sits after the context-hygiene spine from Phase 61 through Phase 92:

- Phase 61 created ContextPacket schema and receipts.
- Phase 62 and 62B added truth-gated selection and blocked-risk preservation.
- Phase 63 through Phase 75 added eligibility, preflight, source-kind, handoff, dry-run, constraint, adapter, compliance, shadow, audit, and guardrail contracts.
- Phase 76 through Phase 83 added adversarial tests, policy decisions, operator review, synthetic/internal candidates, display boundaries, and internal model-call review gates.
- Phase 84 through Phase 88 added non-sendable provider dry-run, review, fixed-stub simulation, and network-egress review/preflight contracts.
- Phase 89 proved the null transport moves zero bytes.
- Phase 90 made the transport registry null-only.
- Phase 91 defined transport capability metadata while keeping real registration forbidden.
- Phase 92 defined credential custody metadata while keeping real secrets forbidden.

## Endpoint custody manifest is not endpoint custody

The manifest is posture metadata only. It can declare no-endpoint posture, forbidden findings, future evidence gaps, Phase 91/92 linkage metadata, no-endpoint/no-secret/no-runtime/no-network proof markers, and deterministic digests. It is not authorization to custody, resolve, validate, or use an endpoint.

## No-endpoint invariant

A clean manifest is `endpoint_custody_no_endpoints`; a clean preflight is `endpoint_preflight_no_endpoints_allowed`. Even that allowed state means metadata-only compatibility, not endpoint use. Endpoint values, endpoint references, resolver access, DNS access, environment/file/config-store access, credentials, provider clients, network authority, provider send, sockets, HTTP, provider SDKs, semantic generation, memory, actions, retention, routing, admission, and execution remain forbidden.

## Future endpoint contract placeholder

`endpoint_custody_future_endpoint_contract_placeholder` is metadata-only. It must not contain a resolvable URL, hostname, IP address, port, DNS name, endpoint path, environment variable intended to resolve an endpoint, config-store key/path, credential, client/session/transport handle, or request/response handle.

## Preflight behavior

The preflight denies by default and allows only no-endpoint metadata compatibility when the manifest is clean, requested kind is one of the allowed placeholder kinds, all no-endpoint/no-runtime/no-network/no-secret flags remain true, and Phase 91/92 linkages remain null-only/no-secret metadata. It never mutates the Phase 90 registry, Phase 91 capability manifests, Phase 92 credential manifests, or any runtime state.

## Endpoint detection behavior

Detection is conservative and scans metadata field names/values for endpoint-like or endpoint-adjacent markers including URL schemes, localhost/address markers, host/hostname/port terms, DNS/resolve terms, socket/connect/request/session/client terms, provider-domain terms, config/file/env references, and credential-adjacent markers such as authorization, bearer, token, and secret. Explicit negative marker names such as `endpoint_resolution_forbidden` and `does_not_make_network_calls` remain metadata-only and are not treated as endpoint evidence.

## Digest behavior

Manifest and preflight digests are deterministic over stable fields. Digests change when endpoint kind, declared/forbidden properties, endpoint flags, linked Phase 91/92 digests, requested kinds, requested access flags, findings/warnings/constraints/gaps, or no-endpoint/no-runtime/no-network markers change. Digests do not include prompt text, raw payloads, credentials, endpoint handles, provider handles, network handles, runtime handles, model/provider params, or nondeterministic timestamps.

## Guardrail behavior

The Phase 75 static guardrail scans `prompt_provider_endpoint_custody.py` by default. The module must not import or call prompt assembly, memory, action, retention, routing, provider SDK, HTTP, socket, DNS, environment, file/config/vault/keychain/cloud-secret, LLM, provider, or runtime APIs. Endpoint terms in the module are metadata-only schema/denial labels, not endpoint access.

## Tests

Phase 93 tests cover clean manifest/preflight behavior, forbidden endpoint custody kinds, endpoint-like marker denial, requested access denial, Phase 91/92 linkage gates, no-endpoint/no-runtime marker denial, digest determinism/change behavior, mutation safety, guardrail coverage, and architecture/import-purity integration.

## Deferred work

Future endpoint custody review, real transport endpoint review, DNS isolation review, network egress execution, provider client construction, credential binding, and live provider transport remain deferred and forbidden by this phase.
