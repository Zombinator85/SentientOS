# Phase 62 Truth-Gated Context Selector Execplan

## Goal
Implement a pure context-selection contract that takes normalized context candidates and emits a non-authoritative Phase 61 `ContextPacket` with explicit inclusion/exclusion reasoning.

## Non-goals
- No prompt assembly integration.
- No memory retrieval changes.
- No truth runtime behavior changes.
- No action, embodiment runtime, or retention side effects.

## Selector contract
- Input: candidate list + scope + mode + time + optional budget.
- Output: immutable Phase 61 `ContextPacket`.
- Packet invariants: non-authoritative, decision power none, no memory write/admit/execute behavior.

## Candidate shape
`ContextCandidate` includes ref identity/type, scope fields, summary, provenance refs, timestamps, freshness/contradiction/truth ingress statuses, priority, and metadata.

## Inclusion rules
- Include only provenance-complete candidates.
- Include claims only when source-backed claims include evidence refs.
- Include dialogue only when scoped and provenance-bearing.
- Include stance only when stance refs and provenance are complete.
- Include sanitized embodiment summaries only (raw embodiment excluded in Phase 62).

## Exclusion rules
- Missing ref_id.
- Missing provenance refs.
- Expired candidates.
- Truth ingress blocked states (`blocked`, `unsupported`, `underconstrained`, etc.).
- Contradiction blocked state.
- Scope mismatch.
- Unknown ref type.

## Tests
- Added Phase 62 selector tests covering eligibility, exclusions, contradiction warning caveats, provenance semantics, lane separation, append-only receipt compatibility, and import purity.

## Deferred work
- Full embodiment/privacy integration and policy-enforced context transformation (Phase 63).
- Runtime wiring into prompt assembly pipeline.
