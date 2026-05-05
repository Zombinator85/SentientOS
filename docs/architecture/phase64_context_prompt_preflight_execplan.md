# Phase 64: Context Packet Prompt-Eligibility Preflight Contract

## Goal
Define a pure, deterministic preflight contract that evaluates whether a selected `ContextPacket` is eligible for downstream prompt assembly handoff.

## Non-goals
- No wiring to `prompt_assembler.py`.
- No prompt assembly behavior changes.
- No memory, truth, embodiment, action, retention, routing, admission, orchestration, or execution runtime changes.

## Dependency chain
- Phase 61: packet schema + receipts.
- Phase 62: truth-gated selection.
- Phase 62B: `PollutionRisk.BLOCKED` packet contamination preservation.
- Phase 63: embodiment/privacy adapters producing selector-compatible candidates.

## Invariant
Selection is not prompt eligibility.

## Hard block rules
Preflight blocks prompt eligibility on blocked risk, provenance gaps, truth/contradiction unsafe status, privacy/biometric/raw-retention unsanitized posture, raw perception and legacy raw modality artifacts, action/retention/feedback/admission-routing-execution capability, authority violations, empty packets, and schema validation failures.

## Caveat rules
Preflight allows `prompt_eligible_with_caveats` for high-risk but non-blocked packets, sanitized+explicitly allowed sensitive context, contradiction/freshness caveats that are non-blocking, and scoped non-authoritative diagnostic contexts.

## Handling classes
Privacy, biometric/emotion, and raw-retention are fail-closed unless sanitized and explicitly allowed. Action/authority capabilities are fail-closed.

## Output contract
Preflight returns deterministic status, block reasons, caveats, packet identity, risk/provenance summary, categorized ref-id lists, and explicit non-runtime markers (preflight-only, no llm/memory/action/retention/execution effects).

## Tests
`tests/test_phase64_context_prompt_preflight.py` covers prompt eligibility statuses, block/caveat mappings, selector integration, mutation-purity, and import purity.

## Deferred work
Runtime wiring into prompt assembly remains explicitly deferred to a future phase.
