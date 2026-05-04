from __future__ import annotations

from pathlib import Path

from sentientos.embodiment_proposal_diagnostic import (
    build_embodied_proposal_review_summary,
    summarize_recent_embodied_proposals,
)
from sentientos.embodiment_proposals import append_embodied_proposal, build_embodied_proposal_record, list_recent_embodied_proposals
from sentientos.scoped_lifecycle_diagnostic import build_scoped_lifecycle_diagnostic


def _proposal(kind_effect: str, source: str, *, t: float, risk_flags=None, privacy="review"):
    return build_embodied_proposal_record(
        source_module=source,
        gate_mode="proposal_only",
        blocked_effect_type=kind_effect,
        ingress_receipt={"ingress_id": f"i-{source}-{t}", "risk_flags": risk_flags or {}},
        created_at=t,
        privacy_retention_posture=privacy,
    )


def test_phase49_summary_empty() -> None:
    summary = summarize_recent_embodied_proposals([], generated_at=10.0)
    assert summary["recommended_review_posture"] == "no_pending_embodied_proposals"
    assert summary["proposal_count_total"] == 0
    assert summary["pending_review_count"] == 0
    assert summary["counts_by_kind"] == {}
    assert summary["counts_by_source_module"] == {}
    assert summary["non_authoritative"] is True
    assert summary["decision_power"] == "none"


def test_phase49_summary_mixed_risk_and_stable_recent_refs() -> None:
    proposals = [
        _proposal("memory_write", "mic_bridge", t=1.0),
        _proposal("feedback_action", "feedback", t=2.0),
        _proposal("retention:screen_ocr", "screen_awareness", t=3.0, risk_flags={"emotion_sensitive": True}),
        _proposal("retention:multimodal:scene_voice", "multimodal_tracker", t=4.0, risk_flags={"biometric_sensitive": True}),
    ]
    summary = summarize_recent_embodied_proposals(proposals, generated_at=11.0)
    assert summary["counts_by_kind"]["memory_ingress_candidate"] == 1
    assert summary["counts_by_kind"]["feedback_action_candidate"] == 1
    assert summary["counts_by_source_module"]["mic_bridge"] == 1
    assert summary["counts_by_source_module"]["multimodal_tracker"] == 1
    assert summary["high_risk_counts"]["memory_write_pressure"] == 1
    assert summary["high_risk_counts"]["action_trigger_pressure"] == 1
    assert summary["high_risk_counts"]["privacy_sensitive_retention"] == 2
    assert summary["high_risk_counts"]["multimodal_retention"] == 1
    assert summary["recommended_review_posture"] == "pending_mixed_high_risk_review"
    assert summary["most_recent_proposal_refs"][0].startswith("proposal:")


def test_phase49_read_list_integration(tmp_path: Path) -> None:
    path = tmp_path / "embodied_proposals.jsonl"
    append_embodied_proposal(_proposal("memory_write", "mic_bridge", t=1.0), path=path)
    append_embodied_proposal(_proposal("retention:vision_emotion", "vision_tracker", t=2.0), path=path)
    recent = list_recent_embodied_proposals(path=path, limit=20)
    summary = build_embodied_proposal_review_summary(path=path, limit=20, generated_at=20.0)
    assert len(recent) == 2
    assert summary["proposal_count_total"] == 2
    assert summary["pending_review_count"] == 2


def test_phase49_scoped_lifecycle_additive_integration(tmp_path: Path) -> None:
    proposal_path = tmp_path / "logs/embodiment_proposals.jsonl"
    append_embodied_proposal(_proposal("memory_write", "mic_bridge", t=1.0), path=proposal_path)
    diagnostic = build_scoped_lifecycle_diagnostic(tmp_path)
    assert "scope" in diagnostic
    assert "actions" in diagnostic
    assert "embodiment_proposal_review_summary" in diagnostic
    summary = diagnostic["embodiment_proposal_review_summary"]
    assert summary["decision_power"] == "none"
    assert summary["does_not_trigger_feedback"] is True
    assert summary["does_not_write_memory"] is True
