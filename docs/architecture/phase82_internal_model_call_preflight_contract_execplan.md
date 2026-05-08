# Phase 82: Internal Model-Call Preflight Contract Execution Plan

## Goal

Add a pure internal `InternalModelCallPreflight` artifact that evaluates whether Phase 80 internal prompt candidates, Phase 81 display receipts, and Phase 74/77/78 evidence are eligible to be considered by a future internal model-call review gate.

## Non-goals

- No LLM/model/provider call.
- No prompt text egress to providers.
- No memory retrieval, memory write, feedback, retention, action/tool execution, routing, admission, fulfillment, or orchestration.
- No modification to `prompt_assembler.py` or live `assemble_prompt(...)` behavior.
- No provider SDK imports and no runtime model-call path.

## Dependency chain: Phase 61 through Phase 81

Phase 82 consumes the context-hygiene spine as evidence only:

1. Phase 61 context packet schema and receipts.
2. Phase 62 truth-gated selection.
3. Phase 62B blocked-risk preservation.
4. Phase 63 embodiment/privacy context eligibility adapters.
5. Phase 64 prompt preflight.
6. Phase 65 packet-local safety metadata.
7. Phase 66 source-kind safety contracts.
8. Phase 67 prompt handoff manifest.
9. Phase 68 prompt dry-run envelope.
10. Phase 69 prompt assembly constraint verifier.
11. Phase 70 prompt assembly adapter contract.
12. Phase 71 prompt assembler compliance harness.
13. Phase 72 shadow adapter preview.
14. Phase 73 shadow blueprint.
15. Phase 74 audit receipt/attestation.
16. Phase 75 static prompt-boundary guardrails.
17. Phase 76 adversarial failure-mode tests.
18. Phase 77 policy decision layer.
19. Phase 78 operator review receipts.
20. Phase 79 synthetic-only prompt candidate harness.
21. Phase 80 internal/operator-visible no-LLM prompt candidate.
22. Phase 81 internal display/egress receipt boundary.

## Preflight is not model invocation

The preflight produces only metadata: eligibility status, reasons/findings, warnings, required mitigations, digest linkage, provider-absence proof, and explicit no-runtime markers. It never invokes models and never sends candidate text to a provider.

## Rings and statuses

Metadata-only rings:

- `model_review_preflight_only`
- `internal_model_call_review_queue`
- `internal_model_call_dry_run_forbidden_provider`
- `live_model_call_forbidden`

Statuses:

- `model_call_preflight_denied`
- `model_call_preflight_ready_for_review`
- `model_call_preflight_ready_with_warnings`
- `model_call_preflight_review_required`
- `model_call_preflight_invalid_input`
- `model_call_preflight_display_denied`
- `model_call_preflight_policy_denied`
- `model_call_preflight_provider_forbidden`
- `model_call_preflight_runtime_authority_detected`

The default posture is denied. No status authorizes a provider call.

## Provider absence proof

The implementation proves provider absence by:

- Importing no provider SDKs or web clients.
- Rejecting provider/model/LLM configuration and known parameter aliases in input mappings.
- Emitting `provider_call_allowed=False` and `llm_call_allowed=False` on every output.
- Preserving `provider_call_forbidden=True`, `llm_call_forbidden=True`, `does_not_call_llm=True`, and `does_not_send_to_provider=True` markers.
- Being included in the Phase 75 static prompt-boundary guardrail scan.

## Gating rules

The preflight denies or invalidates missing/invalid candidates, missing/invalid display receipts, display denial, digest mismatches, policy denial or shadow-only policy, audit receipts that do not allow shadow materializer preconditions, missing/expired/mismatched review evidence when required, live model-call rings, provider/model/LLM parameters, false no-runtime constraints, runtime authority markers, raw payload markers, authority markers outside allowed internal labels, blocked upstream statuses, disabled feature flags, non-internal display scopes, non-internal/non-operator-visible/non-LLM candidates, and missing internal no-LLM/not-sent-to-model/operator-visible markers.

## Digest behavior

`preflight_digest` is deterministic over stable preflight-safe fields: status, rings, candidate/display/policy/audit/review IDs and digests, packet identity, findings, warnings, mitigations, provider/no-runtime allowances, and explicit boundary markers. It excludes raw payloads, provider handles, runtime handles, model/provider parameter payloads, and nondeterministic timestamps.

The digest changes when candidate, display, policy, audit, or review digest linkage changes; when requested ring changes; when feature-flag-derived findings change; when findings/warnings/mitigations change; or when provider/no-runtime constraint flags change.

## Guardrail behavior

`scripts/verify_context_hygiene_prompt_boundaries.py` scans `sentientos/context_hygiene/prompt_model_call_preflight.py` by default. The module must remain free of provider SDK imports, web-client imports, prompt assembler imports, memory/runtime/action/retention/routing/execution imports, direct `assemble_prompt(...)` calls, provider call helpers, and tool/action/runtime handles.

## Tests

`tests/test_phase82_internal_model_call_preflight_contract.py` covers valid readiness, warnings with accepted review, invalid/missing artifacts, policy/audit/display denial, review-required behavior, provider/model/LLM parameter denial, no-runtime constraints, marker denial, digest determinism and linkage changes, mutation safety, provider absence, adversarial marker denial, guardrail inclusion, and display receipt preservation.

## Deferred work

Future phases may define an internal provider dry-run or model-call review gate, but Phase 82 deliberately stops before that boundary. Any future phase must consume this preflight as a precondition and still prove provider absence until a separate, explicit provider-call contract is approved.
