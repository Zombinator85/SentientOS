# Phase 75 Context Hygiene Prompt Boundary Guardrails Execplan

## Goal
Phase 75 adds CI-friendly static guardrails that enforce the context-hygiene shadow prompt assembly boundary before any prompt text materialization is permitted. The guardrails fail on source/AST evidence of prompt materialization fields, forbidden runtime imports, forbidden runtime calls, or bypass paths around the Phase 61-74 contract chain.

## Non-goals
- Do not materialize prompt text.
- Do not assemble final prompts.
- Do not call LLMs, provider SDKs, tools, browser controllers, or hardware adapters.
- Do not retrieve memory or write memory.
- Do not trigger feedback, commit retention, admit work, route work, execute work, or orchestrate runtime behavior.
- Do not change live `assemble_prompt(...)` behavior or any production prompt assembler call site.
- Do not modify truth, embodiment, action, retention, routing, admission, execution, or orchestration runtime behavior.

## Phase 61 through Phase 74 dependency chain
1. Phase 61 created `ContextPacket` schema and receipts.
2. Phase 62 added truth-gated context selection.
3. Phase 62B made blocked risk first-class and preserved attempted-candidate contamination.
4. Phase 63 added embodiment/privacy context eligibility adapters.
5. Phase 64 added prompt preflight.
6. Phase 65 preserved packet-local safety metadata.
7. Phase 66 added source-kind safety contracts.
8. Phase 67 added prompt handoff manifest.
9. Phase 68 added prompt assembly dry-run envelope.
10. Phase 69 added prompt assembly constraint verifier.
11. Phase 70 added prompt assembly adapter contract.
12. Phase 71 added prompt assembler compliance harness.
13. Phase 72 added prompt assembler shadow adapter preview hook.
14. Phase 73 added prompt assembler shadow blueprint contract.
15. Phase 74 added prompt materialization audit receipt / attestation.

Phase 75 enforces that future changes cannot bypass this chain by directly wiring context-hygiene payloads into prompt materialization or runtime authority surfaces.

## Guardrails are not prompt materialization
The guardrail script reads source text and parses Python AST only. It does not import `prompt_assembler.py`, does not import context-hygiene runtime helpers, and does not execute project runtime modules. Its outputs are boundary reports and findings, not prompt content.

## Static scan targets
The default scan target set is:
- `prompt_assembler.py`
- `sentientos/context_hygiene/prompt_materialization_audit.py`
- `sentientos/context_hygiene/prompt_assembler_compliance.py`
- `sentientos/context_hygiene/prompt_adapter_contract.py`
- `sentientos/context_hygiene/prompt_constraint_verifier.py`
- `sentientos/context_hygiene/prompt_dry_run_envelope.py`
- `sentientos/context_hygiene/prompt_handoff_manifest.py`
- `sentientos/context_hygiene/prompt_preflight.py`
- `sentientos/context_hygiene/context_packet.py`
- `sentientos/context_hygiene/safety_metadata.py`
- `sentientos/context_hygiene/source_kind_contracts.py`
- `sentientos/context_hygiene/selector.py`

## Forbidden fields, imports, and calls
The scanner fails on prompt-materialization and runtime-authority identifiers such as `final_prompt_text`, `assembled_prompt`, `prompt_text`, `raw_payload`, `execution_handle`, `action_handle`, `retention_handle`, and `retrieval_handle`, except for explicitly negative no-runtime marker names such as `does_not_contain_final_prompt_text` and `does_not_materialize_prompt_text`.

It fails context-hygiene prompt-boundary modules that import runtime/provider surfaces such as `memory_manager`, `openai`, `requests`, `httpx`, browser/tool control modules, action/retention/routing/admission/execution surfaces, embodiment runtime adapters, or raw screen/audio/vision/multimodal adapters.

It fails context-hygiene prompt-boundary modules that call `assemble_prompt(...)`, provider/LLM creation or generation methods, memory retrieval/write methods, retention commits, feedback triggers, action execution, work routing/admission/execution/orchestration, or browser/mouse/keyboard/tool control calls.

## Shadow allowlist
Phase 75 keeps a compact allowlist for intentional shadow-only names introduced in Phases 72-74:
- `preview_context_hygiene_adapter_payload_for_prompt_assembly`
- `build_context_hygiene_shadow_prompt_adapter_preview`
- `build_context_hygiene_shadow_prompt_blueprint`
- `build_shadow_prompt_blueprint_from_adapter_payload`
- `PromptAssemblerShadowAdapterPreview`
- `PromptAssemblerShadowBlueprint`
- `PromptMaterializationAuditReceipt`
- `audit_receipt_allows_shadow_materializer`

These names are allowed by name only. Their implementations are still scanned for forbidden runtime imports, forbidden runtime calls, and forbidden prompt-text fields.

## CLI behavior
Run:

```bash
python scripts/verify_context_hygiene_prompt_boundaries.py
```

Expected behavior:
- exits `0` when the default scan is clean;
- exits nonzero when boundary findings exist;
- prints compact human-readable findings by default;
- supports `--json` for deterministic JSON output;
- accepts optional paths to scan temporary fixtures or changed files.

## Tests
`tests/test_phase75_context_hygiene_prompt_boundary_guardrails.py` covers:
- clean default scanning;
- deterministic reports and summaries;
- injected forbidden field/import/call fixtures;
- negative marker allowlisting;
- Phase 72-74 shadow-name allowlisting;
- `prompt_assembler.py` shadow import boundary checks;
- CLI success/failure behavior;
- import-purity and no optional pyttsx3/eSpeak dependency expectations;
- preservation of Phase 74 and architecture test surfaces.

## Deferred work
- Future phases may add a synthetic materializer only after these guardrails remain green and the materializer has a separate explicit boundary contract.
- Future docs scans may add live-integration wording checks if drift appears in architecture documentation.
- Future architecture manifests may classify this script as a dedicated static/CI boundary enforcement layer if the manifest grows per-script classifications.
