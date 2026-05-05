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
