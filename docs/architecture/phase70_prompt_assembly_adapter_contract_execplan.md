# Phase 70 Prompt Assembly Adapter Contract Exec Plan

## Goal

Phase 70 adds a pure Prompt Assembly Adapter Contract that converts a Phase 69 verified `PromptAssemblyCandidatePlan` into a bounded adapter payload shape for a future prompt assembler. The adapter payload is non-authoritative, deterministic, and explicitly dry-wired.

## Non-goals

- No changes to `prompt_assembler.py`.
- No prompt assembly and no final prompt text.
- No LLM calls or LLM parameter transport.
- No memory retrieval or memory writes.
- No action, retention, feedback, routing, execution, orchestration, or admission behavior.
- No source rehydration and no raw memory, screen, audio, vision, multimodal, browser, mouse, or keyboard payloads.

## Dependency chain

- Phase 61 created the `ContextPacket` schema and receipts.
- Phase 62 added truth-gated context selection.
- Phase 62B made `BLOCKED` first-class and preserved attempted-candidate contamination.
- Phase 63 added embodiment/privacy context eligibility adapters.
- Phase 64 added prompt preflight.
- Phase 65 preserved packet-local safety metadata.
- Phase 66 added per-source-kind safety contract completeness.
- Phase 67 added the prompt handoff manifest.
- Phase 68 added the prompt assembly dry-run envelope.
- Phase 69 added the prompt assembly constraint verifier.
- Phase 70 consumes Phase 69 verification plus the verified candidate plan and emits only an adapter contract payload.

## Adapter is not prompt assembly

The adapter contract is a preparation-only schema. It never concatenates summaries into final prompt prose, never emits system/developer/user prompt text, and never grants runtime authority. Its payload is safe input shape only; a future prompt assembler must still enforce its own prompt-generation logic and boundaries.

## Adapter payload is not final prompt text

The payload contains IDs, statuses, bounded summaries, constraints, notes, caveats, violations, warnings, sections, refs, and no-runtime markers. It does not contain `prompt_text`, `final_prompt_text`, `assembled_prompt`, raw payloads, hidden chain-of-thought, execution handles, retrieval handles, action handles, retention handles, or LLM parameters.

## Adapter status mapping

| Phase 69 verifier status | Phase 70 adapter status |
| --- | --- |
| `constraint_verified` | `adapter_ready` |
| `constraint_verified_with_warnings` | `adapter_ready_with_warnings` |
| `constraint_failed` | `adapter_blocked` |
| `constraint_not_applicable` | `adapter_not_applicable` |
| `constraint_invalid_envelope` | `adapter_invalid_verification` |
| `constraint_invalid_candidate_plan` | `adapter_invalid_candidate_plan` |

## Adapter ref and section rules

Adapter refs are derived only from verified candidate-plan refs and may include ref identity, ref type, lane, content summary, provenance refs, source kind, privacy posture, pollution risk, caveats, and safety summary.

Allowed section kinds are:

- `adapter_context_refs`
- `adapter_diagnostic_refs`
- `adapter_evidence_refs`
- `adapter_embodiment_refs`
- `adapter_caveat_requirements`
- `adapter_provenance_boundaries`
- `adapter_privacy_boundaries`
- `adapter_truth_boundaries`
- `adapter_safety_boundaries`
- `adapter_constraint_summary`

Sections summarize contract boundaries only. They do not assemble prose and do not merge summaries into final prompt text.

## Gating behavior

- `constraint_verified` and `constraint_verified_with_warnings`: include adapter refs.
- `constraint_failed`: include no adapter refs and preserve violations.
- `constraint_not_applicable`: include no adapter refs.
- `constraint_invalid_envelope` and `constraint_invalid_candidate_plan`: include no adapter refs and preserve violations.

Failed, not-applicable, and invalid material is therefore never made to appear usable by the adapter layer.

## Digest rules

The adapter digest is a deterministic SHA-256 over stable adapter-safe fields. It changes when verification status, refs, warnings, violations, caveats, assembly constraints, or notes change. It excludes raw payloads, final prompt text, and runtime handles by construction because those fields are not part of the adapter payload contract.

## Relationship to Phase 69 verifier

Phase 70 does not re-verify source truth or re-run raw selection. It trusts the Phase 69 verification object as the gate and maps that verification into adapter readiness. Convenience builders may construct the Phase 68 envelope, default Phase 69 candidate plan, and Phase 69 verification from an envelope or packet, but they still stop at adapter payload construction.

## Tests

`tests/test_phase70_prompt_assembly_adapter_contract.py` covers status mapping, identity fields, constraints, sections, gated refs, caveats, provenance/privacy/truth/safety notes, warnings, violations, no-prompt/no-raw/no-authority helpers, digest determinism and sensitivity, envelope and packet builders, Phase 63-to-70 flow, Phase 62B blocked safety, input immutability, and import purity.

## Deferred work

- Runtime integration with any prompt assembler remains deferred.
- Actual prompt text assembly remains deferred.
- Additional downstream assembler validation remains deferred.
- UI or operator presentation of adapter payloads remains deferred.
