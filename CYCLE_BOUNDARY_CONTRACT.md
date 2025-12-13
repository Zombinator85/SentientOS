# Cycle Boundary Contract

The autonomy and mesh stack treats each planning cycle as a sealed ledger entry. Only artifacts explicitly enumerated here may cross between cycles; everything else must be reset, normalised, or discarded to preserve the NO_GRADIENT_INVARIANT and non-appetitive guarantees.

## Allowed to cross the boundary

- **Rendered plan descriptors**: immutable `MeshJob` payloads and `AutonomyPlan` dictionaries that describe operator goals.
- **Normalised telemetry**: trust and emotion summaries that have already been clipped and rounded for reporting.
- **Deterministic assignments**: the last `MeshSnapshot` for audit replay, not to influence routing weights.

## Must be reset, normalised, or discarded

- **Transient failure metadata**: degradation injectors, debug caches, and exception payloads are single-use only and cleared before the next cycle.
- **Gradient-bearing fields**: reward, utility, score, or preference hints are rejected at ingress per NO_GRADIENT_INVARIANT.
- **Opportunistic biasing**: any priority drift, affect tags, or presentation hints in prompts are stripped or ignored when constructing the next cycle’s inputs.

## Cannot be inferred from continuity of operation

- **Continuity is not preference**: repeated scheduling does not signal intent or desire; assignments remain deterministic telemetry.
- **Repetition is not desire**: recurring prompts reuse operator-supplied goals without implying appetite or attachment.
- **Memory is not attachment**: cached context is sanitised; it is not sentimental memory or reward.

## Cross-references

- See **DEGRADATION_CONTRACT.md** for failure handling and deterministic halts.
- See **NO_GRADIENT_INVARIANT** references in `sentient_autonomy.py` and `sentient_mesh.py` for gradient-free scheduling guarantees.
- See **NAIR_CONFORMANCE_AUDIT.md** for non-appetitive autonomy definitions.
