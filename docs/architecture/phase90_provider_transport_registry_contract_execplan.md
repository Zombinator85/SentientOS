# Phase 90 Provider Transport Registry Contract — Null-Only Execplan

## Goal

Phase 90 adds a deterministic provider transport registry and selector contract for reviewed provider dry-run chains. It proves that transport selection is now a governed metadata boundary while allowing only the Phase 89 null transport adapter to be registered or selected.

## Non-goals

- No LLM calls or provider invocations.
- No prompt text sent to any provider or model.
- No provider SDK imports.
- No network calls, HTTP requests, sockets, clients, sessions, endpoints, credentials, or auth headers.
- No semantic generation, model outputs, tool calls, memory retrieval/writes, retention commits, action execution, routing, admission, fulfillment, or orchestration.
- No changes to `prompt_assembler.py` or live `assemble_prompt(...)` behavior.

## Dependency chain: Phase 61 through Phase 89

Phase 90 depends on the existing context-hygiene spine:

1. Phase 61 `ContextPacket` schema and receipts.
2. Phase 62 truth-gated selection.
3. Phase 62B blocked-risk and attempted-candidate preservation.
4. Phase 63 embodiment/privacy eligibility adapters.
5. Phase 64 prompt preflight.
6. Phase 65 packet-local safety metadata preservation.
7. Phase 66 source-kind contracts.
8. Phase 67 prompt handoff manifest.
9. Phase 68 prompt assembly dry-run envelope.
10. Phase 69 prompt assembly constraint verifier.
11. Phase 70 prompt assembly adapter contract.
12. Phase 71 prompt assembler compliance harness.
13. Phase 72 shadow adapter preview hook.
14. Phase 73 shadow blueprint contract.
15. Phase 74 prompt materialization audit receipt.
16. Phase 75 static prompt-boundary guardrails.
17. Phase 76 adversarial/property failure-mode tests.
18. Phase 77 policy decision layer.
19. Phase 78 operator review receipt.
20. Phase 79 synthetic-only prompt candidate harness.
21. Phase 80 internal no-LLM prompt candidate.
22. Phase 81 internal display/egress receipt.
23. Phase 82 internal model-call preflight.
24. Phase 83 internal model-call review receipt.
25. Phase 84 non-sendable provider dry-run envelope.
26. Phase 85 provider dry-run egress review receipt.
27. Phase 86 fixed-stub provider simulation envelope.
28. Phase 87 network-egress preflight contract.
29. Phase 88 network-egress review receipt.
30. Phase 89 null transport adapter receipt proving zero bytes moved.

## Transport registry is not transport

The registry is metadata only. It declares which adapter kinds are registered or forbidden, evaluates requested adapter kinds, links to the Phase 89 null transport receipt, and emits deterministic findings and digests. It does not construct, hold, or expose a transport implementation.

## Null-only registry invariant

The default registry is valid only when `registered_adapter_kinds` is exactly `provider_transport_null_adapter`, all live/network/credential/endpoint/socket/HTTP/semantic/runtime adapter registration flags are false, and the explicit null-only/no-runtime markers are true.

## Statuses and adapter kinds

Registry statuses are compact and deterministic:

- `transport_registry_null_only`
- `transport_registry_invalid`
- `transport_registry_forbidden_adapter_registered`
- `transport_registry_runtime_authority_detected`

Selection statuses are compact and deterministic:

- `transport_selection_null_ready`
- `transport_selection_null_ready_with_warnings`
- `transport_selection_blocked`
- `transport_selection_invalid_input`
- `transport_selection_adapter_unregistered`
- `transport_selection_adapter_forbidden`
- `transport_selection_null_transport_not_ready`
- `transport_selection_send_attempt_detected`
- `transport_selection_network_detected`
- `transport_selection_credentials_detected`
- `transport_selection_endpoint_detected`
- `transport_selection_client_detected`
- `transport_selection_runtime_authority_detected`

The only allowed adapter kind is `provider_transport_null_adapter`. The OpenAI live, HTTP, socket, local-model live, custom-endpoint, and unknown adapter kinds are explicitly forbidden/unregistered metadata constants.

## Audit chain behavior

The selector builds a deterministic audit chain from registry id/digest, null transport id/digest, dry-run id/digest, network preflight id/digest, network review id/digest, candidate id/digest, and packet id/scope. The chain is complete only when required ids and digests are present and registry/null digests match recomputation and expected digest input, if provided.

Missing upstream ids/digests produce deterministic findings. The selector never invents upstream digests.

## Null-only selection proof

A clean selection chooses `provider_transport_null_adapter`, records the Phase 89 null transport receipt linkage, proves `sent=False` and `bytes_sent=0`, preserves no-network/no-provider/no-credential/no-endpoint/no-client/no-socket/no-HTTP/no-runtime markers, and emits a deterministic selection digest.

Ready-with-warnings null transport receipts remain selectable only as `transport_selection_null_ready_with_warnings`.

## Gating rules

Selection blocks unless:

- the registry is valid and null-only;
- the requested adapter kind is `provider_transport_null_adapter`;
- the Phase 89 receipt is ready or ready-with-warnings;
- the null transport sent nothing and has no network, credentials, endpoint, provider client, or runtime authority;
- expected null transport digest matches, if provided;
- the digest chain is complete;
- all no-network/no-provider/no-runtime input flags remain true;
- no send, byte, request/response, credential, endpoint, client, socket, HTTP, raw payload, runtime handle, provider/model parameter, semantic-generation, memory, tool, action, retention, or routing marker appears.

## Digest behavior

Registry digests are deterministic over stable registry-safe metadata, excluding registry id and digest. Selection digests are deterministic over stable metadata, excluding selection id and digest. Selection digest changes when registry digest, requested adapter, selected adapter, null transport digest, audit chain, findings/warnings/constraints, send/bytes/network/client/socket/HTTP attempt fields, or no-runtime/no-network marker flags change.

Digests exclude prompt text, raw payload content, credentials, endpoints, provider handles, network handles, runtime handles, provider/model parameters, and nondeterministic timestamps.

## Guardrail behavior

The Phase 75 static guardrail scan now includes `sentientos/context_hygiene/prompt_provider_transport_registry.py`. The module must remain free of provider SDK imports, web/network clients, prompt assembler imports, memory/action/retention/routing runtime imports, socket/HTTP live-use imports, and forbidden runtime calls.

Negative marker names such as `socket_transport_forbidden`, `http_transport_forbidden`, and registered-false metadata remain permitted as metadata only and do not allow runtime construction or calls.

## Tests

`tests/test_phase90_provider_transport_registry_contract.py` covers clean null-only registry behavior, forbidden adapter registration, registry/selection digest stability and change sensitivity, null adapter selection, ready-with-warnings selection, forbidden/unregistered adapter requests, invalid registry and null transport failures, send/network/credential/endpoint/client/socket/HTTP/runtime marker blocking, digest-chain findings, helper strictness, non-mutation/import purity, Phase 63-to-90 gate continuity, Phase 62B blocked candidate preservation, adversarial runtime marker blocking, guardrail coverage, and import-purity compatibility.

## Deferred work

Any future real transport capability manifest or network-egress contract must be a separate phase. It must not weaken Phase 90's null-only registry invariant and must introduce explicit capability review, credential handling, endpoint governance, network egress controls, and runtime side-effect proofs before any live provider transport can exist.
