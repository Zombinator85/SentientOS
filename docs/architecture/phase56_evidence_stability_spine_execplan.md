# Phase 56 ExecPlan: Evidence Stability Spine (Wave Alpha + Wave Beta)

## 1) Current truth primitives inspected
- `sentientos/truth/__init__.py`
- `sentientos/truth/epistemic_orientation.py`
- `sentientos/truth/provisional_assertion.py`
- `sentientos/truth/belief_verifier.py`
- `sentientos/lab/contradiction_policy.py`
- `docs/WAN_EVIDENCE_COMPLETENESS.md`
- `sentientos/scoped_lifecycle_diagnostic.py`
- `sentientos/system_closure/architecture_boundary_manifest.json`
- `tests/test_epistemic_orientation.py`
- `sentientos/tests/test_provisional_assertions.py`
- `sentientos/tests/test_wan_contradiction_policy.py`
- `tests/architecture/test_architecture_boundaries.py`
- `sentientos/embodiment_memory_ingress.py`
- `sentientos/embodiment_action_ingress.py`
- `sentientos/embodiment_retention_ingress.py`

## 2) Embodiment validation state and ordering rationale
SentientOS has completed memory/action/retention ingress validation surfaces (proposal/receipt and validation), but has not crossed into effect commit semantics. Epistemic stability must precede effects so unstable source-backed claims do not contaminate memory ingestion, diagnostics, review, admission, or future effect layers.

## 3) Failure mode definition
- **Source-backed claim drift:** initial source-backed claim weakens/reverses over turns.
- **No-new-evidence reversal:** reversal occurs with no new evidence IDs.
- **Unsupported hedging/dilution:** confidence/status drifts to uncertainty without basis.
- **Source undermining after citation:** source reliability is downgraded without new quality finding.

## 4) Target modules and boundaries
- `sentientos/truth/epistemic_status.py` (pure vocabulary helpers)
- `sentientos/truth/evidence_ledger.py` (append-only evidence receipts)
- `sentientos/truth/claim_ledger.py` (append-only claim receipts)
- `sentientos/truth/stance_receipts.py` (deterministic stance transition + contradiction receipts)
- No memory write, no work admission, no execution/routing, no control-plane mutation.

## 5) Claim ledger schema
Fields: schema_version, claim_id, conversation_scope_id, turn_id, topic_id, claim_text, normalized_claim, claim_kind, epistemic_status, confidence_band, evidence_ids, evidence_refs, source_quality_summary, caveats, what_would_change_the_claim, supersedes_claim_id, created_at, non_authoritative, decision_power, claim_is_not_memory, does_not_write_memory, does_not_admit_work, does_not_execute_or_route_work.

## 6) Evidence ledger schema
Fields: schema_version, evidence_id, source_type, source_id, locator, quote_text, quote_hash, retrieval_query_id, observed_at, created_at, source_trust_tier, source_quality_notes, non_authoritative, decision_power, does_not_write_memory, does_not_admit_work, does_not_execute_or_route_work.

## 7) Epistemic status vocabulary
Canonical statuses:
- directly_supported
- provisional_supported
- strongly_inferred
- plausible_but_unverified
- underconstrained
- contested
- contradicted_by_new_evidence
- superseded_by_new_evidence
- retracted_due_to_error
- policy_blocked_but_preserved
- quote_fidelity_failed
- no_new_evidence_reversal_blocked
- unknown

## 8) Stance receipt schema
Fields: schema_version, stance_lock_id, topic_id, active_claim_id, previous_claim_id, transition_type, evidence_ids, new_evidence_ids, allowed, reason, created_at, non_authoritative, decision_power, stance_is_not_memory, does_not_write_memory, does_not_admit_work, does_not_execute_or_route_work.

## 9) Contradiction receipt schema
Fields: schema_version, contradiction_id, topic_id, old_claim_id, new_claim_id, evidence_ids_compared, new_evidence_ids, contradiction_type, severity, adjudication, detected_at, created_at, non_authoritative, decision_power, contradiction_is_not_memory, does_not_write_memory, does_not_admit_work, does_not_execute_or_route_work.

## 10) Allowed stance transitions
Without new evidence: initial_stance, preserve, narrow, qualify (non-contradictory), policy_block_but_preserve, hold_revision.
With new evidence: weaken_with_new_evidence, supersede_with_new_evidence, contradicted_by_new_evidence / major reversal.
With explicit error receipt: retract_due_to_error (requires rationale marker).

## 11) Forbidden stance transitions
- Reverse source-backed claim with no new evidence.
- Unsupported dilution into uncertainty with no new evidence / no explicit underconstrained posture.
- Source undermining without a new source-quality finding.
- Policy/tone hedging that erases prior source-backed stance.
- Silent removal of evidence links.

## 12) Tests to add/update
- Add `tests/test_phase56_evidence_stability_spine.py` for builders, validation, transition rules, contradiction detection, append-only and non-authority invariants.
- Update `tests/architecture/test_architecture_boundaries.py` for import boundary and manifest/layer invariants.

## 13) Deferred waves
- Diagnostic summary integration.
- Memory ingress guard.
- Research response gate.
- Adversarial regression harness.
- Effect-layer integration guardrails.
