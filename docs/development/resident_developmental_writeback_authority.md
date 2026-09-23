# Resident developmental writeback authority

The bounded runtime is now optionally composed into the resident cadence as
documented in [resident developmental cognition](resident_developmental_cognition.md).
Composition preserves separate candidate-specific control-plane admission and
the rule that tick-N writes cannot be retrieved until a later completed tick.

## Why this shape exists

SentientOS now has a callable canonical resident path that can turn selected evidence into bounded, attributable developmental history and later test whether retrieval changes cognition. The authority definition remains eligibility vocabulary rather than a grant: every append consumes a separately issued, exact runtime admission, and the controller never mints that admission. The runtime schedules no cognition, changes no prompt, and creates no goal or host/repository effect.

The sole principal is `deterministic_resident_developmental_writeback_controller`. Its exact effect surface is:

1. `exact_world_state_evidence_snapshot_read`
2. `bounded_governed_local_developmental_inference_request`
3. `exact_resident_developmental_candidate_observation`
4. `bounded_resident_developmental_history_append`
5. `exact_resident_developmental_history_retrieval`
6. `exact_resident_developmental_source_provenance_read`
7. `resident_developmental_writeback_receipt_write`
8. `read_only_resident_developmental_history_projection`

The implementation task is complete, while each runtime operation still requires separate exact runtime control-plane admission. World-State supplies evidence, not authority. Governed-local-model machinery performs the independently admitted, one-call bounded `resident_developmental_interpretation` purpose, but this capability grants no generic model authority.

## Distinct stages and truth

The conceptual composition is: World-State **evidence** → governed local **interpretation** → untrusted typed **developmental candidate** → exact **admission** → bounded durable **historical record** → provenance-preserving **retrieval** → measured **changed later cognition**. None of those stages is **truth**. In particular:

> **memory != current truth**

Evidence identifies an observation; interpretation records a source-bound transformation; a candidate remains untrusted; admission establishes only eligibility for an exact write; storage proves only retention; retrieval proves only availability; and changed cognition requires a causal measurement. Contradictions and revisions must remain visible. A successful future experiment must compare later cognition under controlled retrieval conditions rather than equating storage with learning.

Canonical explicit user retention remains a separate authority. Developmental writeback cannot silently widen it or mutate canonical user memory. Model output and observed evidence cannot authorize their own persistence; retention authority must come from the independently admitted control plane and produce an audit receipt.

## Implemented bounded runtime

`sentientos/resident_developmental_writeback.py` implements explicit bounded World-State fact selection with source membership and digest validation; a strict structured governed-local-model request; a whitelist-parsed, content-addressed untrusted candidate; exact admission consumption bound to candidate, operation, principal, and the complete effect set; and an atomic, immutable developmental-history record and receipt store. Exact replay is idempotent, while digest or identity conflict fails closed.

Retrieval is exact-ID, bounded, and read-only. Its projection carries explicit false fields for current truth, authority, policy, and canonical explicit user retention. A new controller constructed over the same root verifies and retrieves prior records. The deterministic measurement surface compares supplied with-record and withheld-record cognition observations and reports only whether their cognition digests differ; it does not infer improvement, learning, correctness, selfhood, or consciousness.

The developmental-history root is distinct from canonical explicit user-retention storage. Historical disagreements are retained rather than overwritten, and selected conflicts and source provenance remain in the record. A record's existence proves durable retention only, not retrieval or causal influence.

## Emergence hygiene and deferred composition

The design rule is **minimal developmental authorship, maximal causal legibility**, with **hard boundaries, soft interior**. A future substrate may constrain provenance, evidence identity, authority boundaries, bounded record format, admission criteria, receipts, retrieval limits, contradiction visibility, and measurement hooks. It must not hardcode interpretation content, personality, emotional state, approval-seeking, survival, novelty, empowerment, identity narrative, or a developmental destination. Constraint is not motivation.

This capability creates no goals, preferences, appetites, identity, policy, host effects, repository effects, or proof of selfhood or consciousness. Default resident composition and scheduling, production longitudinal experiments, model-replacement experiments, broad contradiction/revision policy, and generalized reversible retention/forgetting policy remain deferred.

The exact future implementation goal is:

> "Implement one canonical resident path over selected evidence that performs bounded developmental writeback with source-bound transformation provenance, preserves the invariant memory is not current truth; supports subsequent retrieval and measured changed cognition, and preserve canonical explicit user retention."

The bounded callable runtime portion of that goal is implemented. The broader developmental loop is not resident by default, autonomously composed, or longitudinally demonstrated.
