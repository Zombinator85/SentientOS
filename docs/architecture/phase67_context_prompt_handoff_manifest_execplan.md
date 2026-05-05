# Phase 67: Context Prompt Handoff Manifest (Execution Plan)

## Goal
Define a pure contract artifact that summarizes `ContextPacket + prompt preflight` into auditable handoff metadata.

## Non-goals
- No prompt assembly.
- No prompt text generation.
- No runtime wiring/admission/routing/execution.

## Dependency chain
Phase 61 packet schema/receipts → 62 truth gating → 62B blocked contamination → 63 embodiment/privacy eligibility → 64 prompt preflight → 65 packet safety metadata preservation → 66 source-kind safety contract completeness.

## Status mapping
- `prompt_eligible` → `handoff_ready`
- `prompt_eligible_with_caveats` → `handoff_ready_with_caveats`
- `prompt_ineligible_*` → `handoff_blocked`
- `prompt_ineligible_empty_packet` → `handoff_not_applicable`
- packet schema failure → `handoff_invalid_packet`

## Summary rules
Included ref summaries are allowlisted packet-safe fields only (ids, lane/type, summary, provenance summary, safety summary, caveats). No raw payloads/handles/prompt text/runtime controls.

Lane summaries aggregate count, worst pollution risk, provenance completeness, source kinds, caveats, blocked/unsafe count, rationale.

## Digest rules
Deterministic SHA256 over stable manifest-safe fields. Changes when refs/preflight/block reasons/caveats/safety summaries/risk/provenance change.

## Preflight relationship
Manifest accepts optional preflight; computes preflight internally when omitted.

## Receipts relationship
Receipts unchanged: they already provide append-only selection provenance; manifest is separate non-executing contract output.

## Tests
See `tests/test_phase67_context_prompt_handoff_manifest.py`.

## Deferred work
Future prompt assembly integration can consume manifest, but Phase 67 remains boundary-only.
