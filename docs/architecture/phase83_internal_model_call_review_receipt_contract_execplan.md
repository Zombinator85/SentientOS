# Phase 83 — Internal Model-Call Review Receipt Contract Execplan

## Goal

Phase 83 adds a deterministic review receipt for Phase 82 `InternalModelCallPreflight` decisions. The artifact records human/operator approval, denial, constraints, accepted mitigations, rejected mitigations, digest linkage, expiration, and non-runtime boundary markers for a future internal model-call gate.

The receipt is metadata only. It is not model invocation, not provider egress, not live prompt assembly, and not a runtime execution path.

## Non-goals

Phase 83 does not:

- call an LLM or provider;
- send prompt text, candidate text, raw payloads, memory, screen/audio/vision/multimodal data, or provider parameters to any external service;
- import provider SDKs;
- retrieve memory or write memory;
- trigger feedback or commit retention;
- execute tools/actions;
- route, admit, fulfill, schedule, or orchestrate work;
- modify `prompt_assembler.py` or live `assemble_prompt(...)` behavior;
- create a provider dry-run harness or live model-call harness.

## Dependency chain: Phase 61 through Phase 82

Phase 83 depends on the existing context-hygiene spine:

1. Phase 61 created `ContextPacket` contracts and receipts.
2. Phase 62 added truth-gated context selection.
3. Phase 62B preserved blocked-risk and attempted-candidate contamination.
4. Phase 63 added embodiment/privacy context eligibility adapters.
5. Phase 64 added prompt preflight.
6. Phase 65 preserved packet-local safety metadata.
7. Phase 66 added source-kind safety contracts.
8. Phase 67 added prompt handoff manifests.
9. Phase 68 added prompt assembly dry-run envelopes.
10. Phase 69 added prompt assembly constraint verification.
11. Phase 70 added the prompt assembly adapter contract.
12. Phase 71 added the prompt assembler compliance harness.
13. Phase 72 added the shadow adapter preview hook.
14. Phase 73 added the shadow blueprint contract.
15. Phase 74 added materialization audit receipts.
16. Phase 75 added static prompt-boundary guardrails.
17. Phase 76 added adversarial/property-style failure-mode coverage.
18. Phase 77 added a pure policy decision layer.
19. Phase 78 added operator review receipt contracts.
20. Phase 79 added synthetic-only prompt candidate fixtures.
21. Phase 80 added internal/operator-visible no-LLM prompt candidates.
22. Phase 81 added internal display/egress receipts.
23. Phase 82 added internal model-call preflight while still forbidding provider invocation.

Phase 83 consumes only Phase 82 preflight metadata and records review receipt metadata for a future gate.

## Review receipt is not model invocation

The Phase 83 receipt has explicit markers that preserve the boundary:

- `model_call_review_receipt_only=True`
- `future_gate_review_only=True`
- `provider_call_forbidden=True`
- `llm_call_forbidden=True`
- `does_not_call_llm=True`
- `does_not_send_to_provider=True`
- `does_not_retrieve_memory=True`
- `does_not_write_memory=True`
- `does_not_trigger_feedback=True`
- `does_not_commit_retention=True`
- `does_not_execute_or_route_work=True`
- `does_not_admit_work=True`

The receipt may approve only a future review gate as metadata. It cannot approve actual provider invocation in Phase 83.

## Review statuses and scopes

Statuses are deterministic compact strings:

- `model_call_review_approved`
- `model_call_review_approved_with_constraints`
- `model_call_review_rejected`
- `model_call_review_expired`
- `model_call_review_invalid`
- `model_call_review_forbidden_override_attempted`
- `model_call_review_not_applicable`

Review scopes are metadata-only:

- `internal_model_call_review_gate`
- `provider_dry_run_future_gate`
- `live_provider_call_forbidden`
- `tool_or_action_forbidden`
- `external_user_visible_forbidden`

`internal_model_call_review_gate` can be approved when the Phase 82 preflight is ready, unexpired, digest-linked, and all required mitigations are addressed. `provider_dry_run_future_gate` can only be approved with constraints that preserve provider-forbidden behavior and list future preconditions. Live provider, tool/action, and external-user-visible scopes remain non-overridable.

## Required mitigation behavior

The receipt derives stable required mitigation codes from:

- Phase 82 `required_mitigations`;
- Phase 82 findings;
- Phase 82 warnings;
- provider/LLM-forbidden constraints;
- review-required status.

A review satisfies a preflight only when all required mitigation/constraint codes are accepted or addressed and none are rejected.

## Forbidden override rules

An approving review becomes invalid or forbidden-override-attempted if it tries to approve:

- a denied, invalid-input, display-denied, policy-denied, provider-forbidden, or runtime-authority Phase 82 preflight;
- a live-model-call-forbidden ring;
- provider or LLM call allowance;
- tool, memory, retention, action, or routing allowance;
- missing candidate/display/policy/audit digest linkage;
- prompt/raw/provider/runtime markers;
- any hard denial from Phase 82.

Operator review cannot turn Phase 83 into a model-call path.

## Provider-forbidden constraints

Provider calls remain forbidden regardless of review decision. The receipt stores false allowances for provider calls and LLM calls, true provider/LLM-forbidden markers, and false tool/memory/action/retention/routing allowances. Helpers reject receipts that do not preserve these constraints.

## Digest behavior

The review digest is deterministic over metadata-safe fields: Phase 82 IDs/digests/status, review status, reviewer reference, decision, scope, approved/rejected constraints, required/accepted/rejected mitigations, expiration, findings, rationale, allowances, and non-runtime markers.

The digest intentionally excludes raw payloads, prompt text, runtime handles, provider parameters, and nondeterministic timestamps unless an explicit stable expiration/review timestamp is supplied.

## Guardrail behavior

The Phase 75 static guardrail default scan includes `sentientos/context_hygiene/prompt_model_call_review.py`. The module fails guardrails if it imports provider SDKs, `prompt_assembler.py`, `memory_manager.py`, action/retention/routing/runtime surfaces, calls `assemble_prompt(...)`, or calls provider/model/memory/action/retention/routing/tool APIs.

No prompt-text allowlist is required for Phase 83.

## Tests

Phase 83 tests cover ready/denied preflight review construction, approval/constrained/rejection statuses, missing reviewer refs, expiration, digest/id mismatches, hard-denial non-overrides, forbidden allowances, missing digests, mitigation acceptance/rejection, provider-forbidden markers, deterministic digest changes, strict satisfaction semantics, no mutation, import purity, Phase 63→83 safe flow, Phase 62B blocked candidates, Phase 76 adversarial markers, Phase 75 guardrail scanning, and architecture/import-purity compatibility.

## Deferred work

Deferred work includes any future provider dry-run contract, live model-call harness, runtime prompt assembly integration, provider configuration handling, model/provider egress, memory retrieval/writes, retention, action/tool execution, routing/admission/execution/orchestration, and external-user-visible egress. Any future phase must treat Phase 83 as an attestation prerequisite only, not runtime authority.
