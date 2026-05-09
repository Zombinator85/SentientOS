# Phase 91 Provider Transport Capability Manifest Execplan

## Goal

Phase 91 adds a pure Provider Transport Capability Manifest and registration-preflight contract for provider transport adapters. The artifact can describe proposed transport capabilities, compute forbidden/incomplete/null-only compatibility findings, produce deterministic digests, and prove that any registration review remains metadata-only.

## Non-goals

Phase 91 does not register, enable, instantiate, or select any real transport. It does not call an LLM, send prompt text, import provider SDKs, make network calls, create endpoints, create clients or sessions, open sockets, perform HTTP requests, retrieve or write memory, commit retention, execute tools/actions, route/admit/orchestrate work, or change live `assemble_prompt(...)` behavior.

## Dependency chain: Phase 61 through Phase 90

Phase 91 depends on the context-hygiene spine already established by Phases 61-90:

- Phase 61: ContextPacket schema and receipts.
- Phase 62 / 62B: truth-gated selection plus blocked-risk preservation.
- Phase 63-66: embodiment/privacy eligibility, prompt preflight, safety metadata, and source-kind contracts.
- Phase 67-76: handoff manifests, dry-run envelopes, constraint verification, adapter/compliance/shadow/audit/guardrail/adversarial contracts.
- Phase 77-83: policy, operator review, internal candidate/display/model-call preflight and review contracts.
- Phase 84-88: provider dry-run, egress review, fixed-stub simulation, network-egress preflight, and network-egress review contracts.
- Phase 89: null transport receipt proving zero bytes moved.
- Phase 90: null-only provider transport registry where only `provider_transport_null_adapter` is selectable.

## Capability manifest is not transport registration

`ProviderTransportCapabilityManifest` is a declaration and denial artifact. It records adapter capability metadata, forbidden findings, missing evidence, future-work gaps, deterministic evidence, and explicit no-runtime/no-network markers. It does not mutate the Phase 90 registry and cannot create a provider transport.

## Null-only capability invariant

Only `transport_capability_null_adapter` can produce `transport_capability_null_only`. A clean null-only manifest must declare no forbidden capabilities, contain complete null-only evidence, keep all real transport/runtime capability flags false, and keep all no-network/no-runtime markers true.

## Real transport capabilities remain forbidden

Live provider, network egress, HTTP, socket, provider SDK, credentialed, endpoint, provider client, streaming, tool-calling, semantic-generation, memory-access, action-execution, retention-commit, routing-execution, and unknown capabilities are forbidden. Capability flags for those authorities produce forbidden, detected, incomplete, or runtime-authority statuses rather than registration authority.

## Registration preflight behavior

`ProviderTransportRegistrationPreflight` accepts a capability manifest, the Phase 90 registry manifest, a requested adapter kind, and metadata-only no-runtime/no-network flags. It allows only a null-only no-op compatibility decision when the manifest is clean null-only, the registry is digest-valid and null-only, the requested adapter is `provider_transport_null_adapter`, and every no-runtime/no-network marker remains true. Any real adapter request, forbidden capability, invalid registry, incomplete evidence, runtime marker, raw payload marker, provider parameter marker, or false no-runtime/no-network flag denies or forbids registration.

## Digest behavior

Capability digests are deterministic over stable manifest fields and exclude nondeterministic timestamps, prompt text, raw payloads, credentials, endpoints, provider handles, network handles, runtime handles, and provider/model parameters. Registration-preflight digests are deterministic over stable preflight fields and change when capability evidence, registry digest, requested adapter, requested registration, findings, warnings, constraints, gaps, or no-runtime/no-network marker flags change.

## Guardrail behavior

The Phase 75 static guardrail scan includes `sentientos/context_hygiene/prompt_provider_transport_capability.py` by default. Negative/forbidden marker names and metadata-only capability field names are treated as declarations, while provider SDK imports, network clients, socket/HTTP modules, prompt assembler imports/calls, memory/action/retention/routing imports or calls, provider/model calls, and runtime side effects remain forbidden.

## Tests

`tests/test_phase91_provider_transport_capability_manifest.py` covers clean null-only manifests, forbidden real capabilities, capability flags, missing evidence, deterministic digests, null-only registration preflight, registry non-mutation, forbidden adapter requests, invalid registries, no-runtime/no-network marker failures, runtime marker evidence, helper predicates, Phase 90 null-only preservation, adversarial metadata blocking, and guardrail coverage.

## Deferred work

Future real transport work requires a separate security, privacy, credential custody, network-egress, and operator/council review contract. Phase 91 is only a prerequisite evidence surface and grants no runtime or registration authority.
