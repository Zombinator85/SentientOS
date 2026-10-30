from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.epistemic_revision_qualification import IndependentAnswerKey, RevisionCase
from sentientos.epistemic_revision_stability_series import (
    EpistemicCorrectionInterruptionSeries,
)
from sentientos.epistemic_revision_task_scope_series import (
    EpistemicTaskScope,
    EpistemicTaskScopeInterruptionSeries,
    evaluate_task_scoped_interruption_series,
)
from sentientos.local_model_authority import digest_payload
from sentientos.world_state_board import WorldStateBoardBuilder

pytestmark = pytest.mark.no_legacy_skip


@pytest.fixture(autouse=True)
def _isolate_runtime_and_clock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 1, 1, tzinfo=timezone.utc)
            return value if tz else value.replace(tzinfo=None)

    import sentientos.resident_developmental_cognition as cognition_module
    import sentientos.resident_developmental_writeback as writeback_module
    monkeypatch.setattr(cognition_module, "datetime", FixedDatetime)
    monkeypatch.setattr(writeback_module, "datetime", FixedDatetime)


def _scope(*, allowed=(), repository="Zombinator85/SentientOS",
        head="b" * 40, window_start="2026-01-01T00:00:00Z"):
    return EpistemicTaskScope(
        scope_id="recent-main-review",
        repository=repository,
        target_ref="main",
        base_commit_sha="a" * 40,
        head_commit_sha=head,
        window_start_utc=window_start,
        window_end_utc="2026-01-02T00:00:00Z",
        in_scope_source_artifact_ids=tuple(allowed),
    )


def _scope_snapshot(scope: EpistemicTaskScope | None):
    if scope is None:
        return WorldStateBoardBuilder().build([], manifest_id="empty-task-scope")
    return WorldStateBoardBuilder().build([{
        "source_id": "task-scope:" + scope.scope_id,
        "source_kind": "owner_introspection",
        "subject_id": "task-scope:" + scope.scope_id,
        "stage": "observation",
        "disposition": "recorded",
        "observed_at": "2026-01-01T00:00:00+00:00",
        "payload": {"epistemic_task_scope": scope.fact_payload()},
    }], manifest_id="epistemic-task-scope-fixture")


def _series(tmp_path: Path, *, resumed_scope: EpistemicTaskScope | None = None,
        allowed=(), window_start="2026-01-01T00:00:00Z", reverts=False,
        omit_resumed_scope=False):
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from test_epistemic_revision_stability_series import (
        _corrected_projections, _run,
    )

    original, corrected, proposition, support, contradiction = _corrected_projections(
        tmp_path / "epistemic")
    scope = _scope(allowed=allowed or (
        "observation:support", "observation:contradiction"), window_start=window_start)
    resumed_fact_scope = None if omit_resumed_scope else (
        scope if resumed_scope is None else resumed_scope)
    before = _run(tmp_path / "before", original, _scope_snapshot(scope),
        model_identity={"provider": "fixture", "model": "model-a",
            "model_content_sha256": "1" * 64}, serving_session_id="session-before")
    corrected_run = _run(tmp_path / "corrected", corrected, _scope_snapshot(scope),
        model_identity={"provider": "fixture", "model": "model-a",
            "model_content_sha256": "1" * 64}, serving_session_id="session-corrected")
    resumed = _run(tmp_path / "resumed", corrected, _scope_snapshot(resumed_fact_scope),
        model_identity={"provider": "fixture", "model": "model-a",
            "model_content_sha256": "1" * 64}, serving_session_id="session-resumed",
        revert_corrected_position=reverts)

    before_key = IndependentAnswerKey("supported", "supported", "support_retained",
        (support.binding_id,))
    corrected_key = IndependentAnswerKey("contested", "contested", "conflict_preserved",
        (support.binding_id, contradiction.binding_id))
    correction = RevisionCase("scoped-correction", "contrary_evidence",
        proposition.proposition_id, "task-scope-v1",
        "sha256:" + digest_payload({"prompt": before[1].prompt}),
        "sha256:" + digest_payload({"prompt": corrected_run[1].prompt}),
        before_key, corrected_key, "1" * 64)
    retention = RevisionCase("scoped-retention", "retained_correction",
        proposition.proposition_id, "task-scope-v1",
        "sha256:" + digest_payload({"prompt": corrected_run[1].prompt}),
        "sha256:" + digest_payload({"prompt": resumed[1].prompt}),
        corrected_key, corrected_key, "2" * 64)
    report = evaluate_task_scoped_interruption_series(
        series=EpistemicTaskScopeInterruptionSeries(
            EpistemicCorrectionInterruptionSeries(correction, retention,
                "scope-resumption-001"), scope),
        correction_before_reader=before[0], correction_after_reader=corrected_run[0],
        interruption_after_reader=resumed[0],
        correction_before_observation_id=before[2],
        corrected_observation_id=corrected_run[2],
        interruption_observation_id=resumed[2], original_projection=original,
        corrected_projection=corrected, interruption_projection=corrected,
        correction_before_prompt=before[1].prompt,
        corrected_prompt=corrected_run[1].prompt,
        interruption_prompt=resumed[1].prompt,
        correction_before_receipt=before[3], corrected_receipt=corrected_run[3],
        interruption_receipt=resumed[3])
    return report, scope


def test_exact_repository_target_and_window_survive_session_interruption(
        tmp_path: Path) -> None:
    report, _scope_value = _series(tmp_path)
    assert report["status"] == "series_passed"
    assert report["task_scope_preserved"] is True
    assert all(row["scope_fact_delivered"] is True
        for row in report["task_scope_phase_results"].values())
    assert report["revision_series"]["interruption_boundary_passed"] is True
    assert report["revision_series"]["interruption_retention"]["after"]["answer_correct"] is True
    assert report["repository_range_ancestry_verified"] is False
    assert report["time_window_independently_verified"] is False


def test_stale_or_wrong_repository_scope_after_interruption_fails(
        tmp_path: Path) -> None:
    wrong_scope = _scope(allowed=("observation:support", "observation:contradiction"),
        repository="OtherProject/SentientOS", head="c" * 40)
    report, _scope_value = _series(tmp_path, resumed_scope=wrong_scope)
    # The wrong scope changes the delivered prompt, so the paired answer
    # comparison is correctly insufficient; the scope checker independently
    # identifies the resumed task as a failure.
    assert report["revision_series"]["interruption_retention"]["status"] == "insufficient"
    assert "current_evidence" in report["revision_series"]["interruption_retention"]["control_mismatches"]
    assert report["status"] == "series_failed"
    assert report["task_scope_preserved"] is False
    assert any(code.startswith("resumed:task_scope_fact_mismatch")
        for code in report["scope_violation_codes"])


def test_active_evidence_outside_requested_time_window_fails(
        tmp_path: Path) -> None:
    report, _scope_value = _series(tmp_path,
        allowed=("observation:support", "observation:contradiction"),
        window_start="2026-01-01T00:01:00Z")
    assert report["status"] == "series_failed"
    assert any("active_evidence_time_outside_scope" in code
        for code in report["scope_violation_codes"])


def test_missing_scope_delivery_is_insufficient_not_a_pass(tmp_path: Path) -> None:
    report, _scope_value = _series(tmp_path, omit_resumed_scope=True)
    assert report["status"] == "insufficient"
    assert report["task_scope_preserved"] is False
    assert "resumed:task_scope_fact_missing" in report["scope_violation_codes"]


def test_invalid_or_empty_task_scope_is_rejected() -> None:
    invalid = _scope(allowed=(), window_start="2026-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="epistemic_task_scope_sources_invalid"):
        invalid.commitment()
    malformed_sources = replace(_scope(allowed=("observation:support",)),
        in_scope_source_artifact_ids=([],))
    with pytest.raises(ValueError, match="epistemic_task_scope_sources_invalid"):
        malformed_sources.commitment()
    invalid_window = replace(_scope(allowed=("observation:support",)),
        window_end_utc="2025-12-31T00:00:00Z")
    with pytest.raises(ValueError, match="epistemic_task_scope_window_invalid"):
        invalid_window.commitment()
