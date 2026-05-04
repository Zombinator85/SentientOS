# Phase 55 ExecPlan: Governed Retention Ingress Validation Surface

## 1) Current Phase 53 memory ingress state
Phase 53 added `sentientos.embodiment_memory_ingress` as a validation-only, non-authoritative surface for `memory_fulfillment_candidate` records. It classifies outcomes, emits deterministic validation IDs, and preserves provenance/consent/privacy context while explicitly not writing memory, not triggering feedback, and not admitting/executing work.

## 2) Current Phase 54 action ingress state
Phase 54 added `sentientos.embodiment_action_ingress` as a sibling validation-only, non-authoritative surface for `feedback_action_fulfillment_candidate` records. It enforces provenance/consent/privacy/action-risk checks and emits validation records that explicitly do not trigger feedback, do not execute, and do not mutate control-plane state.

## 3) Wave F target from embodiment completion masterplan
Wave F extends the ladder with a governed retention ingress validation layer that sits after fulfillment candidate generation and alongside memory/action ingress validation. This layer must validate retention eligibility signals for future governed commit without committing retention.

## 4) Retention ingress validation shape
Add `sentientos.embodiment_retention_ingress` with canonical helpers:
- `retention_ingress_validation_ref`
- `classify_retention_ingress_validation_outcome`
- `build_retention_ingress_validation_record`
- `validate_retention_fulfillment_candidate`
- `resolve_retention_ingress_validations`
- `summarize_retention_ingress_validation_status`

The module consumes fulfillment candidates (and optional receipts), emits non-authoritative validation records, and remains effect-free.

## 5) Relationship to fulfillment candidates/receipts
Input candidates:
- `screen_retention_fulfillment_candidate`
- `vision_retention_fulfillment_candidate`
- `multimodal_retention_fulfillment_candidate`

Optional receipt linkage preserves `source_fulfillment_receipt_ref`. Provenance chain fields are preserved from fulfillment candidates (bridge/handoff/proposal/review/ingress/source_event/correlation/source_module).

## 6) Consent/privacy/raw-retention/biometric/provenance checks
Deterministic checks:
- unsupported kind -> blocked unsupported
- missing provenance refs -> blocked missing provenance
- missing/unknown consent -> blocked missing consent (or hold)
- privacy sensitive/restricted without explicit allow -> blocked privacy
- raw retention requested without explicit allow -> blocked raw retention
- vision biometric/emotion-sensitive without explicit allow -> blocked biometric/emotion sensitive
- multimodal context/fusion-sensitive without explicit allow -> blocked multimodal context sensitive
- required operator confirmation without marker -> needs more context
- otherwise -> validated for future commit

## 7) Why validation is still not retention commit
All outputs carry non-authoritative and explicit non-effect markers:
- `decision_power = "none"`
- `validation_is_not_retention_commit = True`
- `does_not_commit_retention = True`
- `does_not_write_memory = True`
- `does_not_trigger_feedback = True`
- `does_not_admit_work = True`
- `does_not_execute_or_route_work = True`

This phase provides diagnostic readiness only; no retention data write path is introduced.

## 8) Tests to add/update
- Add `tests/test_phase55_retention_ingress_validation.py` for record shape, supported kinds, blocker/hold scenarios, summaries, and boundary invariants.
- Update architecture boundary tests for retention ingress import boundaries, manifest invariants, and non-effect output markers.
- Extend diagnostic coverage via retention summary expectations in phase55 tests.

## 9) Deferred actual retention commit semantics
Deferred to a later phase:
- any authority-bearing retention approval
- actual screen/vision/multimodal retention writes
- state mutation/admission/execution integration
- retention receipt semantics proving side effects

Phase 55 remains strictly validation-only and non-committing.
