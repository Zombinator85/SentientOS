# Phase 53 ExecPlan: Fulfillment Coverage Hardening + Governed Memory Ingress Validation

## 1) Current late-stage state (Phases 51/52)
Late-stage ladder coverage exists for handoff, governance bridge, fulfillment candidates, and fulfillment receipts, but focused runs remained skip-heavy due to legacy-skip quarantine markers not being bypassed in all phase files.

## 2) Skip-hardening plan
- Inspect phase 49–52 test files + `tests/conftest.py` legacy-skip policy.
- Add `pytest.mark.no_legacy_skip` to Phase 51/52 files lacking it.
- Keep intentional/explicit skips unchanged.
- Re-run focused phase files and report pass/skip counts.

## 3) Wave D target from masterplan
Introduce the first governed ingress layer after fulfillment:
- `memory_fulfillment_candidate`
- `memory_ingress_validation` (non-authoritative receipt-like diagnostic)
- no memory mutation.

## 4) Memory ingress validation shape
Create `sentientos/embodiment_memory_ingress.py` with:
- deterministic validation id
- validation-only record builder
- resolver over fulfillment candidates
- outcome classifier
- diagnostic summary helper

## 5) Relationship to fulfillment candidates/receipts
Validation consumes fulfillment candidates (and optional fulfillment receipts for traceability), preserving upstream refs:
proposal/review/handoff/bridge/ingress/event/correlation/source metadata.

## 6) Consent/privacy/retention checks
Deterministic rules:
- unsupported kind -> blocked_unsupported_kind
- missing provenance refs -> blocked_missing_provenance
- sensitive/restricted privacy without explicit allow marker -> blocked_privacy_sensitive
- raw retention requested without explicit allow marker -> blocked_raw_retention
- missing/unknown consent -> blocked_missing_consent or needs_more_context
- low-risk + complete provenance + present consent -> validated_for_future_write

## 7) Why validation is still not memory write
All records are explicitly non-authoritative and include invariants:
- `decision_power: none`
- `validation_is_not_memory_write: true`
- `does_not_write_memory: true`
- `does_not_admit_work/execute/trigger_feedback/commit_retention: true`

## 8) Tests to add/update
- Add `tests/test_phase53_memory_ingress_validation.py` for builder, outcomes, blockers, summary posture, boundary invariants.
- Update architecture boundaries test for new layer manifest and forbidden import/non-effect assertions.
- Update phase 51/52 test markers for no-legacy-skip focused execution.

## 9) Deferred semantics
Deferred to later phases:
- actual governed memory append/write
- authority/admission/execution coupling
- feedback/action ingress
- retention commit ingress
