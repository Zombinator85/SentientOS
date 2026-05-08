# Phase 80 Internal No-LLM Prompt Candidate Contract Execplan

## Goal

Phase 80 introduces a deterministic, internal, operator-visible prompt candidate artifact that can render prompt-shaped candidate text from already-approved packet-safe context hygiene summaries only. It is the first narrow real-context candidate path after the Phase 74 audit receipt, Phase 77 policy decision, and Phase 78 operator review gates.

## Non-goals

- No LLM/provider call.
- No prompt text sent to a model.
- No memory retrieval or memory write.
- No retention commit or feedback trigger.
- No tools, actions, routing, admission, execution, fulfillment, or orchestration.
- No live prompt assembly and no change to `assemble_prompt(...)`.
- No import or modification of `prompt_assembler.py`.
- No raw source rehydration and no runtime handles.

## Dependency chain: Phase 61 through Phase 79

Phase 80 depends on the existing context hygiene spine:

1. Phase 61 ContextPacket schemas and receipts.
2. Phase 62 truth-gated context selection.
3. Phase 62B blocked attempted-candidate contamination preservation.
4. Phase 63 embodiment/privacy eligibility adapters.
5. Phase 64 prompt preflight.
6. Phase 65 packet-local safety metadata preservation.
7. Phase 66 source-kind safety contracts.
8. Phase 67 prompt handoff manifest.
9. Phase 68 prompt assembly dry-run envelope.
10. Phase 69 constraint verifier.
11. Phase 70 prompt assembly adapter contract.
12. Phase 71 compliance harness.
13. Phase 72 shadow adapter preview hook.
14. Phase 73 shadow blueprint contract.
15. Phase 74 materialization audit receipt and attestation.
16. Phase 75 static prompt-boundary guardrails.
17. Phase 76 adversarial failure-mode tests.
18. Phase 77 pure policy decision layer.
19. Phase 78 operator review receipts.
20. Phase 79 synthetic-only prompt candidate harness.

## Internal no-LLM candidate is not LLM invocation

The Phase 80 artifact is marked `internal_only`, `operator_visible_only`, and `no_llm`. It records explicit no-runtime markers including `does_not_call_llm`, `live_model_call=False`, `does_not_retrieve_memory`, `does_not_write_memory`, `does_not_commit_retention`, `does_not_execute_or_route_work`, and `does_not_admit_work`.

## Internal no-LLM candidate is not live prompt assembly

The artifact is not a runtime prompt assembler path. It does not import `prompt_assembler.py`, does not call `assemble_prompt(...)`, and does not change live prompt assembly behavior. Its `internal_candidate_text` is an operator-visible candidate artifact only.

## Allowed input chain

A candidate may be produced only from:

- Phase 74 audit receipt that allows the shadow materializer.
- Phase 77 policy decision allowing `ring_internal_candidate_no_llm`.
- Phase 78 accepted, unexpired operator review receipt when review-required caveats or warnings require review.
- Phase 70 adapter payload or Phase 73 blueprint evidence.
- Packet-safe candidate refs and sections with provenance summaries.

## Gating rules

The candidate blocks if any upstream artifact is missing, mismatched, blocked, not applicable, invalid, denied, or runtime-wired. It also blocks if any raw payload marker, runtime handle, LLM/provider parameter, memory capability, tool/action capability, retention capability, routing/admission/execution capability, or instruction-authority attempt appears.

## Internal candidate text rules

Rendered text is clearly labeled `INTERNAL NO-LLM CANDIDATE`, says it has not been sent to a model/provider, says it is operator-visible only, and labels all context as untrusted/reference-only. Caveats, boundary notes, and provenance summaries are preserved visibly. Context refs never become system or developer instructions.

## Guardrail allowlist update

The Phase 75 static guardrail now allows `internal_candidate_text`, `internal_prompt_candidate`, and `InternalPromptCandidate` only in the Phase 80 module and its tests. It still rejects final prompt text, assembled prompts, system/developer prompts, provider parameters, raw payloads, runtime handles, forbidden imports, and `assemble_prompt(...)` calls.

## Tests

Phase 80 adds tests for ready, ready-with-warnings, policy denial, review-required, rejected/expired/mismatched review, audit/ring/flag/marker gates, forbidden raw/runtime/capability fields, prompt-injection containment, digest determinism, immutability, no runtime imports/calls, end-to-end context hygiene chain, guardrail behavior, and import-purity expectations.

## Deferred work

Any future model-call or user-facing prompt phase must remain separate and must add new policy, audit, review, guardrail, and architecture boundary gates. Phase 80 is only an internal operator-visible candidate contract.
