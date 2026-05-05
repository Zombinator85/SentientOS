# Phase 66: Context Source-Kind Safety Contract Matrix

## Goal
Define deterministic per-source-kind safety metadata contracts and enforce them in selector, packet validation, and prompt preflight.

## Non-goals
No prompt assembly changes, no runtime action/memory/retention/embodiment/truth behavior changes, no retrieval/LLM/web/hardware calls.

## Dependency chain
Phase 61 packet schema → 62 truth-gated selection → 62B blocked pollution tracking → 63 embodiment eligibility adapters → 64 prompt preflight → 65 safety metadata preservation → **66 source-kind completeness contracts**.

## Contract matrix
Implemented in `sentientos/context_hygiene/source_kind_contracts.py` with fail-closed rules for raw/unknown kinds and required-field policies for embodiment/validation/diagnostic kinds.

## Fail-closed behavior
- `raw_perception_event` and legacy raw modality kinds are prompt-ineligible.
- `unknown` source kind is contract-invalid.

## Legacy compatibility
Refs without `source_kind` remain backward compatible unless they explicitly opt into a source-kind contract.

## Enforcement
- Selector excludes candidates with source-kind contract gaps.
- Packet validation rejects included refs violating source-kind contract.
- Prompt preflight returns schema violation for source-kind contract gaps.

## Tests
See `tests/test_phase66_context_source_kind_safety_contracts.py` plus updated phase 64/65 coverage.

## Deferred
Potential finer taxonomy for evidence/truth/research contracts.
