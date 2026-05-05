# Context Hygiene Spine

## Separation Contract
- Memory is durable historical substrate.
- Context is bounded, scoped, and temporary selection.
- Truth is adjudicated elsewhere and is not implied by inclusion in context.

## Why Context Packets Exist
Context packets provide an immutable-ish, typed boundary for selected references used in response construction without changing runtime behavior in this phase.

## Non-Authoritative Invariants
- Context packets are non-authoritative.
- Decision power is always `none`.
- Packets do not write memory.
- Packets do not admit, execute, or route work.
- Inclusion and exclusion reasons are retained.
- Validity bounds are mandatory.
- Included references require provenance.

## No Raw Memory Dump Invariant
The schema intentionally separates memory/claim/evidence/stance/diagnostic/embodiment lanes and does not expose any raw memory dump lane.

## Future Integration Points
- **Truth spine:** contradiction/freshness/provenance statuses are explicit and can be consumed by future truth adjudication.
- **Embodiment ladder:** embodiment references are isolated in a dedicated lane for future governed fusion.

## Deferred Work
- Selector
- Distiller
- Pruner
- Prompt adapter / runtime middleware


## Phase 62: Truth-Gated Context Selector Alpha

Phase 62 adds a pure selector layer that evaluates normalized candidates before prompt use. The selector is non-authoritative and returns a Phase 61 `ContextPacket` only.

Key assertions:
- Truth validation is not automatic inclusion.
- Relevance is not equivalent to truth.
- Exclusion reasons are mandatory for every dropped candidate.
- Embodiment privacy/sanitization policy remains deferred to Phase 63 (raw embodiment candidates are excluded by default).


## Phase 62B risk-contract alignment
- `PollutionRisk` supports `low|medium|high|blocked`.
- `blocked` is distinct from `high`: blocked means ineligible for active lanes; high means eligible with caution.
- Packet pollution risk is an assembly-level aggregate over attempted candidates, not only included lanes.
- If any attempted candidate is blocked, packet risk is `blocked` and blocked candidates remain visible in `excluded_refs`/`exclusion_reasons`.
- `provenance_complete` reflects all attempted candidates; included refs remain provenance-bearing.
- This lands before Phase 63 so privacy/embodiment blocked states are preserved instead of silently degrading to `high`.


## Phase 63: Embodiment/Privacy Context Eligibility Bridge
- Raw perception is not context.
- Sanitized embodiment summaries may become context candidates.
- Privacy-sensitive, biometric/emotion-sensitive, raw-retention, and action-capable material is blocked unless explicitly sanitized and allowed.
- This phase is adapter/eligibility only: not prompt assembly, not memory write, and not embodiment runtime behavior.

## Phase 64: Prompt-Eligibility Preflight Contract
- Phase 64 introduces prompt preflight before any prompt-assembly wiring.
- Selection is not prompt eligibility.
- `blocked` packet risk prevents prompt eligibility.
- `high` risk may be prompt-eligible only with explicit caveats.
- Phase 64 does not assemble prompts.
- Phase 64 does not call LLMs.
- Phase 64 does not retrieve or write memory.
- Phase 64 does not modify embodiment, action, or retention runtime behavior.

## Phase 65: Context Safety Metadata Preservation
- ContextPacket lane refs preserve compact packet-safe `context_safety_metadata` evidence for preflight/diagnostics.
- Packets remain auditable without raw-source rehydration.
- Preserved metadata is non-raw and non-authoritative; no prompt assembly/LLM/retrieval/memory-write/runtime action behavior is added.
- This closes the Phase 64 metadata-loss blind spot between selector and prompt preflight.


## Phase 66: Source-kind safety contract matrix
- Safety metadata must be source-kind complete for contract-required kinds.
- Explicit `unknown` source kind fails closed where contracted safety metadata is required.
- Contracts validate evidence metadata only (non-authoritative) and do not grant authority.
- No prompt assembly, LLM calls, retrieval, memory writes, or runtime embodiment/action/retention behavior changes are introduced in this phase.
