# Phase 73: Prompt Assembler Shadow Blueprint Contract Exec Plan

## Goal
Add an opt-in, test-invoked shadow-only blueprint contract in `prompt_assembler.py` that accepts a Phase 70 `PromptAssemblyAdapterPayload`, runs it through the Phase 72 shadow preview/compliance path, and emits a structured future prompt-layout blueprint.

The blueprint proves how compliant adapter refs could be grouped and ordered later without producing prompt text or gaining runtime authority.

## Non-goals
- No final prompt text assembly.
- No concatenation of adapter refs or summaries into prompt prose.
- No LLM calls.
- No memory retrieval or memory writes.
- No feedback, retention, action, routing, admission, execution, orchestration, truth, or embodiment runtime changes.
- No change to `assemble_prompt(...)` behavior or existing call sites.

## Dependency chain
Phase 73 depends on the context hygiene spine:

1. **Phase 61**: `ContextPacket` schema and receipts.
2. **Phase 62**: truth-gated context selection.
3. **Phase 62B**: first-class `blocked` pollution risk and attempted-candidate contamination preservation.
4. **Phase 63**: embodiment/privacy eligibility adapters.
5. **Phase 64**: prompt preflight.
6. **Phase 65**: packet-local safety metadata preservation.
7. **Phase 66**: per-source-kind safety contract completeness.
8. **Phase 67**: prompt handoff manifest.
9. **Phase 68**: prompt assembly dry-run envelope.
10. **Phase 69**: prompt assembly constraint verifier.
11. **Phase 70**: prompt assembly adapter contract.
12. **Phase 71**: prompt assembler compliance harness.
13. **Phase 72**: opt-in shadow prompt assembler adapter preview hook.

## Shadow blueprint is not prompt assembly
The Phase 73 blueprint is a contract artifact only. It carries section descriptors, blueprint-safe ref summaries, caveat requirements, boundary-note requirements, constraints, status mapping, and a deterministic digest. It deliberately omits final prompt text, prompt fragments, raw payloads, raw memory, multimodal raw data, executable handles, retrieval handles, retention handles, action handles, LLM parameters, and browser/mouse/keyboard control data.

## Blueprint output shape
The blueprint includes:

- `blueprint_id`
- `adapter_payload_id`
- `adapter_status`
- `preview_status`
- `blueprint_status`
- `compliance_status`
- `may_future_assembler_consume`
- `must_block_prompt_materialization`
- `adapter_ref_count`
- `blueprint_ref_count`
- `section_count`
- `blueprint_sections`
- `blueprint_refs`
- `preserved_caveats`
- `warnings`
- `violations`
- `assembly_constraints`
- provenance/privacy/truth/safety note-presence booleans
- compact rationale
- deterministic digest
- explicit non-runtime markers

## Section/ref summary rules
Blueprint sections are derived only from Phase 70 adapter sections. Adapter section kinds map to blueprint section kinds:

- `adapter_context_refs` → `blueprint_context_refs`
- `adapter_diagnostic_refs` → `blueprint_diagnostic_refs`
- `adapter_evidence_refs` → `blueprint_evidence_refs`
- `adapter_embodiment_refs` → `blueprint_embodiment_refs`
- `adapter_caveat_requirements` → `blueprint_caveat_requirements`
- `adapter_provenance_boundaries` → `blueprint_provenance_boundaries`
- `adapter_privacy_boundaries` → `blueprint_privacy_boundaries`
- `adapter_truth_boundaries` → `blueprint_truth_boundaries`
- `adapter_safety_boundaries` → `blueprint_safety_boundaries`
- `adapter_constraint_summary` → `blueprint_constraint_summary`

Blueprint refs are derived only from Phase 70 adapter refs and include only metadata-safe fields: ref id, ref type, lane, source kind, privacy posture, pollution risk, provenance ref count, caveat count, and safety-summary presence.

## Digest behavior
The digest is deterministic over stable blueprint-safe fields. It changes when adapter payload id, blueprint status, section/ref summaries, caveats, warnings, violations, constraints, or note-presence booleans change. It excludes raw payloads, final prompt text, runtime handles, LLM parameters, and nondeterministic timestamps.

## Compliance/preview relationship
The builder first calls the Phase 72 preview hook. Preview statuses map to blueprint statuses:

- `shadow_preview_ready` → `shadow_blueprint_ready`
- `shadow_preview_ready_with_warnings` → `shadow_blueprint_ready_with_warnings`
- `shadow_preview_blocked` → `shadow_blueprint_blocked`
- `shadow_preview_not_applicable` → `shadow_blueprint_not_applicable`
- `shadow_preview_invalid_adapter_payload` → `shadow_blueprint_invalid_adapter_payload`
- `shadow_preview_runtime_wiring_detected` → `shadow_blueprint_runtime_wiring_detected`

Ready and ready-with-warnings previews may expose blueprint refs and sections. Blocked, not-applicable, invalid, or runtime-wiring-detected previews expose no blueprint refs or sections and keep prompt materialization blocked.

## Existing behavior preservation
The Phase 73 helper is explicitly invoked by tests only. It does not alter public prompt assembler signatures, does not call `assemble_prompt(...)`, and does not change existing prompt assembly call sites or live behavior.

## Tests
`tests/test_phase73_prompt_assembler_shadow_blueprint_contract.py` covers status mapping, output shape, no-prompt/no-raw/no-runtime markers, section/ref metadata rules, blocked gating, deterministic digest behavior, mutation safety, runtime-call isolation, representative `assemble_prompt(...)` preservation, static scan compatibility, a Phase 63→73 pipeline, and a Phase 62B blocked attempted-candidate path.

## Deferred work
- Real prompt materialization remains deferred.
- Runtime integration remains deferred.
- Any future assembler must re-check compliance, preserve caveats/boundaries, and keep blocked refs non-materialized.
