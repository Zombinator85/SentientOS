# Phase 49 ExecPlan: Embodied Proposal Diagnostic and Operator-Review Visibility

## 1) Current Phase 48 proposal queue state
- `sentientos/embodiment_proposals.py` provides append-only proposal creation and JSONL listing (`build_embodied_proposal_record`, `append_embodied_proposal`, `list_recent_embodied_proposals`).
- Records are explicitly non-authoritative (`decision_power: "none"`, no memory/action/admission/execute flags).
- Queue exists but no canonical compact summary surface for pending review pressure.

## 2) Existing diagnostic/operator surfaces inspected
- `sentientos/embodiment_proposals.py`
- `sentientos/scoped_lifecycle_diagnostic.py`
- `sentientos/orchestration_intent_fabric.py`
- `sentientos/orchestration_spine/projection/current_state.py`
- `sentientos/ledger_api.py`
- scoped lifecycle/orchestration tests in `sentientos/tests/test_orchestration_intent_fabric.py`
- architecture manifest: `sentientos/system_closure/architecture_boundary_manifest.json`
- architecture boundary tests: `tests/architecture/test_architecture_boundaries.py`

## 3) Target visibility shape
Add a compact review summary containing:
- `schema_version`, `summary_id`, `generated_at`
- `proposal_count_total`, `pending_review_count`
- `counts_by_kind`, `counts_by_source_module`
- `high_risk_counts`:
  - `memory_write_pressure`
  - `action_trigger_pressure`
  - `privacy_sensitive_retention`
  - `biometric_or_emotion_sensitive`
  - `multimodal_retention`
- `most_recent_proposal_refs`
- `oldest_pending_created_at`, `newest_pending_created_at`
- `recommended_review_posture`
- explicit non-authority booleans

## 4) Proposal summary/filter strategy
- Introduce read-only helper module `sentientos/embodiment_proposal_diagnostic.py`.
- Consume records from `list_recent_embodied_proposals` (path/limit injectable for tests).
- Filter pending proposals using `review_status == "pending_review"`.
- Group/count deterministically by kind/source/risk from record fields.
- Stable recent refs ordered by `created_at` descending with proposal_id tie-break.

## 5) Non-authority boundaries
- Helper module performs read + summarize only.
- No writes to proposal queue, memory, feedback, admission, task execution, or routing.
- Add explicit summary flags documenting non-authoritative posture.
- Architecture manifest + tests enforce forbidden authority imports and declared read-only posture.

## 6) Tests to add/update
- New focused tests: `tests/test_phase49_embodied_proposal_visibility.py`:
  - empty summary behavior
  - mixed record counts/risk/posture
  - list/read integration via temp JSONL
  - scoped lifecycle diagnostic additive integration
  - non-authority fields
- Update `tests/architecture/test_architecture_boundaries.py`:
  - manifest declaration checks for new layer
  - forbidden import checks on diagnostic modules
  - no legacy perception imports
- Keep existing Phase 48 tests unchanged except compatibility.

## 7) Deferred risks and why
- No approval/rejection/execution workflow is added (out of scope).
- Risk taxonomy remains heuristic from proposal fields; future phases can enrich risk provenance.
- Scoped lifecycle diagnostic growth continues; future refactor may split orchestration and embodiment diagnostics for size/manageability.
