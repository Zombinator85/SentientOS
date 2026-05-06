# Phase 72 Prompt Assembler Shadow Adapter Hook Execution Plan

## Goal
Add the first controlled `prompt_assembler.py` touch for context hygiene: an explicitly invoked, shadow-only adapter preview hook that validates a Phase 70 `PromptAssemblyAdapterPayload` through the Phase 71 prompt assembler compliance harness and returns a compact non-runtime receipt.

## Non-goals
- Do not change live prompt assembly call behavior.
- Do not assemble final prompt text or prompt fragments.
- Do not wire context hygiene into normal runtime prompt assembly paths.
- Do not call LLMs, retrieval, memory, truth runtime, embodiment runtime, action, retention, routing, admission, execution, or orchestration code.
- Do not retrieve memory or write memory.
- Do not treat adapter payloads as authoritative runtime input.

## Dependency chain
- Phase 61 created `ContextPacket` schema and receipts.
- Phase 62 added truth-gated context selection.
- Phase 62B made `BLOCKED` first-class and preserved attempted-candidate contamination.
- Phase 63 added embodiment/privacy context eligibility adapters.
- Phase 64 added prompt preflight.
- Phase 65 preserved packet-local safety metadata.
- Phase 66 added per-source-kind safety contract completeness.
- Phase 67 added the prompt handoff manifest.
- Phase 68 added the prompt assembly dry-run envelope.
- Phase 69 added the prompt assembly constraint verifier.
- Phase 70 added the prompt assembly adapter contract.
- Phase 71 added the prompt assembler compliance harness.

## First controlled `prompt_assembler.py` touch
Phase 72 adds `PromptAssemblerShadowAdapterPreview` and `preview_context_hygiene_adapter_payload_for_prompt_assembly(...)` in `prompt_assembler.py`. The hook is opt-in, test-invoked, and not called by `assemble_prompt(...)` or any existing prompt assembly path.

## Shadow hook is not live prompt assembly
The hook calls only the Phase 71 compliance evaluator, summarizes adapter/compliance status, counts refs/sections, records caveats, notes-presence booleans, warnings, violations, constraints, and explicit non-runtime markers. It never concatenates adapter refs, never returns final prompt text, and never invokes existing prompt assembly functions.

## Preview output shape
The preview includes:
- `preview_id`
- `adapter_payload_id`
- `adapter_status`
- `compliance_status`
- `may_future_assembler_consume`
- `must_block_prompt_materialization`
- `adapter_ref_count`
- `section_count`
- `preserved_caveats`
- provenance/privacy/truth/safety notes-present booleans
- metadata-only `violations` and `warnings`
- compact `constraints`
- compact `rationale`
- explicit non-runtime markers including no prompt assembly, no final prompt text, no LLM calls, no memory retrieval/writes, no feedback/retention, and no execution/routing/admission.

## Compliance relationship
The hook maps Phase 71 statuses to shadow preview status labels in its rationale:

| Phase 71 compliance status | Phase 72 shadow preview status |
| --- | --- |
| `compliance_ready_for_future_integration` | `shadow_preview_ready` |
| `compliance_ready_with_warnings` | `shadow_preview_ready_with_warnings` |
| `compliance_blocked` | `shadow_preview_blocked` |
| `compliance_not_applicable` | `shadow_preview_not_applicable` |
| `compliance_invalid_adapter_payload` | `shadow_preview_invalid_adapter_payload` |
| `compliance_runtime_wiring_detected` | `shadow_preview_runtime_wiring_detected` |

Ready and warning payloads expose metadata counts and boundary notes only. Blocked, not-applicable, invalid, and runtime-wiring-detected payloads report preview status while keeping prompt material blocked.

## Existing behavior preservation
`assemble_prompt(...)` signatures and call sites remain unchanged. The new hook is not invoked from live prompt assembly. Existing prompt assembly behavior continues to use the prior profile, memory, context window, emotion, and action-feedback behavior when callers explicitly call `assemble_prompt(...)`.

## Tests
Phase 72 tests cover ready, ready-with-warnings, blocked, not-applicable, invalid payloads, preview shape, metadata-only caveats/warnings/violations, note booleans, non-runtime markers, no final prompt text/raw payload fields, no runtime authority, no payload mutation, no live prompt assembly calls, representative existing prompt assembly behavior, static scan distinction between shadow hook and live runtime wiring, Phase 63-to-Phase 72 pipeline, Phase 62B blocked-candidate propagation, and import/boundary compatibility.

## Deferred work
A future phase may design a governed live integration path. That work remains deferred and must separately prove prompt materialization, runtime authority, memory access, retention, routing, and orchestration boundaries before any production wiring.
