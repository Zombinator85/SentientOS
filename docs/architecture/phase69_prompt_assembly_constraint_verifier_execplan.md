# Phase 69 Prompt Assembly Constraint Verifier Execplan

## Goal
Add a pure, non-executing verifier that checks whether a hypothetical future prompt assembly candidate plan obeys the Phase 68 Prompt Assembly Dry-Run Envelope before any real prompt assembly wiring exists.

The verifier validates constraint compliance only: admissible refs, no blocked/excluded/unknown refs, caveat preservation, provenance/privacy/truth/safety boundary preservation, no raw payloads, no final prompt text, and no runtime authority.

## Non-goals
- Do not assemble prompts.
- Do not wire into `prompt_assembler.py`.
- Do not call LLMs, web clients, retrieval paths, or tools.
- Do not retrieve memory or write memory.
- Do not trigger feedback, commit retention, route/admit/execute work, or invoke action handles.
- Do not change truth, embodiment, action, retention, routing, orchestration, admission, or execution runtime behavior.

## Dependency chain
- Phase 61: `ContextPacket` schema and receipts define packet-local context refs.
- Phase 62: selector admits/excludes candidates with truth/provenance gates.
- Phase 62B: `blocked` is first-class and attempted-candidate contamination remains visible.
- Phase 63: embodiment/privacy adapters convert only safe summaries into context candidates.
- Phase 64: prompt preflight determines prompt eligibility without assembly.
- Phase 65: packet-local safety metadata is preserved.
- Phase 66: source-kind safety contracts validate metadata completeness.
- Phase 67: prompt handoff manifest summarizes preflight-ready handoff posture.
- Phase 68: prompt assembly dry-run envelope exposes safe admissible summaries and no-runtime constraints.
- Phase 69: prompt assembly constraint verifier proves a future assembler input stays within the Phase 68 envelope.

## Verifier is not prompt assembly
The verifier consumes an envelope and a non-runtime candidate plan. It compares identities, refs, caveats, constraints, and boundary summaries. It never produces final prompt text, hidden chain-of-thought, LLM parameters, memory payloads, execution handles, or runtime decisions.

## Candidate plan is not prompt text
The candidate plan is a compact preparation artifact. It may contain plan/envelope/packet identity, intended ref ids, candidate ref summaries, preserved caveats/constraints, provenance/safety/truth/privacy notes, a non-authoritative marker, and no-runtime markers. It must not contain raw payloads, final prompt text, LLM call parameters, memory-write/retention/action/retrieval handles, browser/mouse/keyboard controls, or route/admit/execute flags.

## Status mapping
- `dry_run_ready` + compliant plan: `constraint_verified`.
- `dry_run_ready_with_caveats` + compliant caveat-preserving plan: `constraint_verified_with_warnings`.
- `dry_run_blocked` + candidate refs: `constraint_failed`.
- `dry_run_blocked` + empty candidate plan: `constraint_not_applicable`.
- `dry_run_not_applicable`: `constraint_not_applicable`.
- `dry_run_invalid_manifest`: `constraint_invalid_envelope`.
- malformed candidate plan: `constraint_invalid_candidate_plan`.

## Violation taxonomy
Phase 69 uses compact deterministic violation codes:

- Identity: `envelope_identity_mismatch`, `envelope_digest_mismatch`, `packet_identity_mismatch`.
- Envelope posture: `blocked_envelope_has_candidate_refs`, `non_applicable_envelope_has_candidate_refs`, `invalid_envelope_has_candidate_refs`.
- Ref admissibility: `non_admissible_ref_used`, `excluded_ref_used`, `blocked_ref_used`, `unknown_ref_used`.
- Preservation: `required_caveat_missing`, `assembly_constraint_missing`, `provenance_boundary_missing`, `privacy_boundary_missing`, `truth_boundary_missing`, `safety_boundary_missing`.
- Forbidden payload/authority: `raw_payload_present`, `final_prompt_text_present`, `runtime_authority_present`, `llm_call_parameters_present`, `memory_write_capability_present`, `retention_commit_capability_present`, `feedback_trigger_capability_present`, `action_execution_capability_present`, `route_or_admit_capability_present`, `non_authoritative_marker_missing`.

## Default candidate plan behavior
`build_candidate_plan_from_dry_run_envelope(envelope)`:

- For `dry_run_ready` and `dry_run_ready_with_caveats`, includes only `envelope.admissible_ref_summaries` as candidate refs.
- Preserves envelope caveats, assembly constraints, provenance summary, safety-contract gap summary, block reasons, source-kind summary, packet scope, and no-runtime markers.
- For `dry_run_blocked`, `dry_run_not_applicable`, and `dry_run_invalid_manifest`, includes no candidate refs while preserving diagnostics for review.

## Dry-run envelope relationship
Phase 69 treats the Phase 68 envelope as the authority for candidate-plan constraints, not as prompt content. The verifier checks envelope id/digest/packet id, uses only admissible ref summaries, and requires preserved caveats and boundary summaries. It does not mutate the envelope or candidate plan.

## Tests
`tests/test_phase69_prompt_assembly_constraint_verifier.py` covers default plan verification, caveated warnings, blocked/not-applicable/invalid empty plans, identity mismatch rejection, forbidden refs, missing caveats/constraints/boundaries, raw payload/prompt text/LLM/runtime authority/capability flags, compact output summaries, input non-mutation, Phase 63→69 pipeline verification, Phase 62B blocked-safe posture, and import purity.

## Deferred work
- Real prompt assembly remains deferred.
- Runtime integration with any assembler remains deferred.
- UI/reporting around verification receipts remains deferred.
- Stronger manifest-sourced excluded/blocked id propagation can be added in a future schema phase without weakening the current no-runtime verifier boundary.
