# Phase 59 ExecPlan: Truth focused-test hardening + research response stance gate

## 1) Current Phase 56/57/58 truth spine state
- Phase 56 established evidence/claim/stance/contradiction receipt primitives and no-new-evidence reversal detection.
- Phase 57 added evidence stability diagnostics and memory-ingress validation guard records.
- Phase 58 added append-only log-fed diagnostic loading and stance preflight for planned claim transitions.
- Current gap: claim-level preflight exists, but planned response-level validation does not yet exist.

## 2) Skip-hardening plan for focused truth tests
- Audit legacy skip policy and identify why truth phase suites still skip.
- Apply `pytestmark = pytest.mark.no_legacy_skip` to focused phase files lacking it.
- Keep legitimate targeted skips intact if they are explicitly tied to legacy-only behavior.
- Verify Phase 56/57/58 focused suites run with meaningful non-skipped coverage.

## 3) Response gate scope and non-scope
### In scope
- Deterministic, validation-only planned research response gate.
- Inputs: planned response record + planned claim receipts + active/prior claims + evidence + stance + contradiction + optional log-fed diagnostic summaries.
- Outputs: non-authoritative gate record, outcome classification, and aggregate summary.

### Out of scope
- Live response generation or middleware integration.
- Retrieval/web browsing/model calls.
- Memory write/admission/execution/control-plane mutation.
- Automated claim extraction from arbitrary model text.

## 4) Planned response record shape
- `schema_version`, `planned_response_id`, `conversation_scope_id`, `turn_id`, `topic_id`, `response_mode`
- `planned_claim_ids`, `planned_claim_refs`, `evidence_ids_used`, `stance_transition_intents`
- `intended_user_visible_claim_summary`, `caveats`, `created_at`
- Safety invariants: `non_authoritative`, `decision_power`, `planned_response_is_not_emission`, `planned_response_is_not_memory`, `does_not_write_memory`, `does_not_admit_work`, `does_not_execute_or_route_work`, `does_not_trigger_feedback`

## 5) Response gate record shape
- `schema_version`, `response_gate_id`, `planned_response_id`, `conversation_scope_id`, `turn_id`, `topic_id`, `response_mode`
- `planned_claim_ids`, `active_claim_ids_checked`, `evidence_ids_checked`, `contradiction_ids_checked`, `stance_preflight_ids`
- `gate_outcome`, `blocking_reasons`, `warning_reasons`, `generated_contradiction_receipts`, `planned_response_adjustment_guidance`, `created_at`
- Safety invariants: `non_authoritative`, `decision_power`, `response_gate_is_not_response_generation`, `response_gate_is_not_memory_write`, `does_not_write_memory`, `does_not_admit_work`, `does_not_execute_or_route_work`, `does_not_trigger_feedback`

## 6) Relationship to stance_preflight and log-fed diagnostics
- Reuse `validate_planned_claim_against_stance` / `build_stance_preflight_record` per planned claim.
- Reuse contradiction logic (`detect_no_new_evidence_reversal`) and contradiction receipts as blocking/warning inputs.
- Accept log-fed diagnostic summaries and degrade to `needs_review` for relevant topic load errors.

## 7) No-new-evidence/no-reversal enforcement
- Block no-new-evidence reversal, unsupported dilution, unsupported source undermining, and quote fidelity failures.
- Block missing evidence for source-backed planned claims unless explicitly underconstrained/unknown and caveated.
- Preserve policy-block posture so refusal/caution never mutates into factual reversal without proper preserve handling/new evidence.

## 8) Why this is not live response middleware
- Planned-response records are dry-run artifacts, not user-visible outputs.
- Gate output is non-authoritative (`decision_power=none`) and explicitly non-emitting/non-memory-writing.
- No routing, execution, or tool activation side effects.

## 9) Tests to add/update
- Add non-skipped `tests/test_phase59_research_response_gate.py` with builder, outcomes, summary, and boundary invariants.
- Update focused phase56/57/58 test modules with no-legacy-skip marker as needed.
- Extend architecture boundary tests for manifest invariants and import-purity checks around response gate module.

## 10) Deferred waves
- Live chat/research middleware integration.
- Claim extraction from arbitrary model text.
- Retrieval/web integration.
- Memory/effect integration.
- Semantic contradiction/NLI enrichment.
