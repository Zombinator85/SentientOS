# Phase 52 ExecPlan: Embodied Fulfillment Candidate + Receipt Surface

## 1) Current Phase 51 handoff/bridge state
Phase 51 ships deterministic, non-authoritative handoff candidates and governance bridge candidates.
The chain currently ends at `sentientos.embodiment_governance_bridge` with explicit invariants:
- approval is not execution
- handoff is not fulfillment
- bridge is not admission
- no memory/action/admission/execution effects

## 2) Wave C target from masterplan
Implement Wave C from `embodiment_completion_masterplan.md`:
- fulfillment candidate surface (derived from governance bridge candidates)
- fulfillment receipt surface (append-only, non-effect classification)
- diagnostic visibility for fulfillment posture

## 3) Fulfillment candidate shape
Add canonical `embodiment.fulfillment_candidate.v1` rows with:
- source refs (bridge/handoff/proposal/review/ingress/events/correlation)
- mapped fulfillment kind
- fulfillment posture (eligible vs blocked reason)
- risk/privacy/consent context and rationale
- strict non-authority/non-effect invariants (`decision_power=none`, no write/trigger/admit/execute)

## 4) Fulfillment receipt shape
Add canonical `embodiment.fulfillment_receipt.v1` rows with:
- source fulfillment candidate refs and upstream refs
- allowed fulfillment outcome classification
- fulfiller kind + label/ref
- rationale + provenance context
- strict non-effect invariants (`fulfillment_receipt_is_not_effect`, `receipt_does_not_prove_side_effect`)

## 5) Allowed fulfillment outcomes
Enumerate and enforce:
- `pending_fulfillment_review`
- `fulfillment_declined`
- `fulfillment_expired`
- `fulfillment_superseded`
- `fulfillment_failed_validation`
- `fulfilled_external_manual`
- `fulfilled_by_governed_path`

These remain classification-only in Phase 52.

## 6) Append-only + provenance strategy
- Build deterministic IDs from stable source material where practical.
- Persist receipts append-only through `sentientos.ledger_api.append_audit_record` to JSONL.
- Keep provenance references in both candidate and receipt rows.

## 7) Why this is still not effect execution
This phase adds only derived candidates and append-only receipts.
It does not call admission/executor/control-plane APIs and does not mutate memory/feedback/retention sinks.
Even “fulfilled_*” outcomes are record labels, not effect proof.

## 8) Diagnostic integration plan
Extend `sentientos.embodiment_proposal_diagnostic.summarize_recent_embodied_proposals` additively with:
- fulfillment candidate count
- counts by candidate kind
- blocked counts by reason
- counts by outcome
- pending review count
- fulfilled receipt count
- fulfillment posture

No existing keys removed or behavior made authoritative.

## 9) Tests to add/update
- New focused suite `tests/test_phase52_embodied_fulfillment.py` for builders/resolvers/append/list/state/summary/boundaries.
- Update architecture boundary tests for:
  - forbidden imports for fulfillment module
  - manifest fulfillment invariants
  - candidate/receipt invariant fields
- Keep Phase 49-51 focused suites green.

## 10) Deferred risks + future Waves D-F
Deferred:
- governed admission linkage semantics
- standardized consent taxonomy breadth
- fulfillment-to-effect receipt correlation contract
Future waves:
- D memory ingress execution path
- E feedback/action governed path
- F retention governed path
All behind explicit consent/policy/admission and effect receipt contracts.
