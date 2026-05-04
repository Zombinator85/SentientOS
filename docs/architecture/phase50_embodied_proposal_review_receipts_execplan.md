# Phase 50 ExecPlan: Embodied Proposal Review Receipts

## 1) Current Phase 48/49 state
- Phase 48 provides append-only proposal records in `sentientos.embodiment_proposals`.
- Phase 49 provides read-only diagnostics in `sentientos.embodiment_proposal_diagnostic` and scoped lifecycle additive inclusion.
- Gap: no canonical append-only review receipt layer for adjudication outcomes.

## 2) Target review receipt shape
- Add `sentientos.embodiment_proposal_review` with compact JSON-serializable review receipt schema.
- Receipt includes proposal provenance, reviewer metadata, outcome, rationale, risk/privacy/consent posture, and explicit non-authority flags.

## 3) Allowed review outcomes
- `pending_review`
- `reviewed_deferred`
- `reviewed_rejected`
- `reviewed_needs_more_context`
- `reviewed_approved_for_next_stage`

## 4) Append-only/provenance strategy
- Append via `sentientos.ledger_api.append_audit_record` to `logs/embodiment_proposal_reviews.jsonl`.
- Deterministic receipt ID from stable hash material.
- Preserve `proposal_id`, `proposal_ref`, ingress ref, source event refs, and correlation id.

## 5) Relationship to future fulfillment/admission
- This phase is non-authoritative and non-executing.
- `reviewed_approved_for_next_stage` is explicitly **not execution** and does not admit work.
- Future admission/fulfillment layers must consume these receipts explicitly and remain separate.

## 6) Tests to add/update
- New focused tests for builder, append/list, resolver, summary integration, and non-authority invariants.
- Update Phase 49 tests for additive review fields.
- Update architecture boundaries test + manifest declaration checks.

## 7) Deferred risks
- No fulfillment/admission coupling yet (deferred to future phase by design).
- No operator UI (deferred).
- No cross-process compaction/indexing for large ledgers (deferred; append-only is sufficient for this phase).
