from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.household_presence_camera_review_chain_summary_packet import (
    FORBIDDEN_NEXT_STEPS,
    build_default_policy,
    evaluate_review_chain_summary_packet,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/household_presence_camera_review_chain_summary_packet")
FALSE_FLAGS = (
    "capture_enabled",
    "capture_available",
    "live_hardware_enabled",
    "raw_media_storage_enabled",
    "speaker_output_enabled",
    "external_disclosure_enabled",
    "summary_grants_operator_consent",
    "summary_renews_operator_grant",
    "summary_enables_live_capture",
    "summary_enables_live_hardware",
    "summary_enables_raw_media_storage",
    "summary_enables_speaker_output",
    "summary_enables_external_disclosure",
    "summary_confers_live_readiness",
    "summary_confers_capture_authorization",
    "summary_schedules_live_review",
    "summary_approves_live_candidate",
    "summary_executes_dry_run",
)


def load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_validates() -> None:
    assert validate_policy(build_default_policy()) == {"ok": True, "status": "household_presence_camera_review_chain_summary_packet_policy_valid"}


def test_missing_required_upstream_evidence_blocks() -> None:
    expected = {
        "missing_review_packet_blocked.json": "review_chain_summary_packet_blocked_missing_review_packet",
        "missing_decision_ledger_blocked.json": "review_chain_summary_packet_blocked_missing_decision_ledger",
        "missing_trend_ledger_blocked.json": "review_chain_summary_packet_blocked_missing_trend_ledger",
        "missing_renewal_request_packet_blocked.json": "review_chain_summary_packet_blocked_missing_renewal_request_packet",
        "missing_dry_run_gate_blocked.json": "review_chain_summary_packet_blocked_missing_dry_run_gate",
        "missing_future_live_deferral_registry_blocked.json": "review_chain_summary_packet_blocked_missing_future_live_deferral_registry",
    }
    for fixture, status in expected.items():
        assert evaluate_review_chain_summary_packet(load(fixture)).status == status


def test_valid_full_chain_metadata_ready_summary_has_non_authority_flags() -> None:
    result = evaluate_review_chain_summary_packet(load("valid_review_chain_metadata_ready.json"))
    assert result.status == "review_chain_summary_packet_ready"
    assert result.packet is not None
    record = result.packet.records[0]
    assert record.summary_conclusion == "review_chain_metadata_ready"
    assert record.no_live_capture_performed is True
    assert all(getattr(record, flag) is False for flag in FALSE_FLAGS)
    assert set(("attempt_capture", "enable_live_capture", "execute_dry_run_capture", "schedule_live_capture_review", "approve_live_candidate", "mark_live_ready", "bypass_future_live_deferral_registry", "infer_operator_consent_from_summary", "convert_summary_to_live_readiness", "convert_summary_to_live_capture_permission", "enable_external_disclosure")).issubset(record.forbidden_next_steps)


def test_summary_conclusion_and_safe_action_variants() -> None:
    expected = {
        "valid_operator_review_required.json": ("review_chain_operator_review_required", "operator_review_required"),
        "valid_operator_grant_required_diagnostic.json": ("review_chain_operator_grant_required", "request_operator_grant_renewal"),
        "valid_proof_refresh_required_diagnostic.json": ("review_chain_proof_refresh_required", "request_dry_run_proof_refresh"),
        "valid_capture_review_packet_rerun_required.json": ("review_chain_capture_review_packet_rerun_required", "rerun_capture_review_packet"),
        "valid_decision_history_review_required.json": ("review_chain_decision_history_review_required", "inspect_decision_history"),
        "valid_trend_history_review_required.json": ("review_chain_trend_history_review_required", "inspect_trend_history"),
        "valid_renewal_request_review_required.json": ("review_chain_renewal_request_review_required", "inspect_renewal_request"),
        "valid_dry_run_gate_review_required.json": ("review_chain_dry_run_gate_review_required", "inspect_dry_run_gate"),
        "valid_future_live_deferral_confirmed.json": ("review_chain_future_live_deferral_confirmed", "maintain_future_live_deferral"),
        "valid_future_live_remains_deferred.json": ("review_chain_future_live_remains_deferred", "maintain_future_live_deferral"),
        "valid_sustain_capture_denial.json": ("review_chain_sustain_capture_denial", "sustain_capture_denial"),
    }
    for fixture, (conclusion, action) in expected.items():
        result = evaluate_review_chain_summary_packet(load(fixture))
        assert result.packet is not None
        record = result.packet.records[0]
        assert record.summary_conclusion == conclusion
        assert action in record.safe_next_actions
        assert record.summary_grants_operator_consent is False
        assert record.summary_renews_operator_grant is False
        assert record.summary_executes_dry_run is False
        assert record.summary_schedules_live_review is False
        assert record.summary_approves_live_candidate is False
        assert record.summary_confers_live_readiness is False


def test_upstream_warning_grant_refresh_future_live_and_dry_run_remain_metadata_only() -> None:
    warning = evaluate_review_chain_summary_packet(load("valid_review_chain_ready_with_warnings.json"))
    assert warning.status == "review_chain_summary_packet_ready_with_warnings"
    grant = evaluate_review_chain_summary_packet(load("valid_operator_grant_required_diagnostic.json"))
    proof = evaluate_review_chain_summary_packet(load("valid_proof_refresh_required_diagnostic.json"))
    for result in (grant, proof):
        assert result.status == "review_chain_summary_packet_ready_with_warnings"
        assert result.packet is not None
        record = result.packet.records[0]
        assert record.summary_grants_operator_consent is False
        assert record.summary_renews_operator_grant is False
        assert record.summary_executes_dry_run is False
        assert record.summary_confers_live_readiness is False
        assert record.future_live_deferred_count >= 1


def test_blocked_boundaries() -> None:
    expected = {
        "upstream_not_ready_blocked.json": "review_chain_summary_packet_blocked_upstream_not_ready",
        "unsafe_live_implication_blocked.json": "review_chain_summary_packet_blocked_unsafe_live_implication",
        "unresolved_denials_blocked.json": "review_chain_summary_packet_blocked_unresolved_denials",
        "scope_mismatch_blocked.json": "review_chain_summary_packet_blocked_scope_mismatch",
        "stale_review_blocked.json": "review_chain_summary_packet_blocked_stale_review",
        "stale_decision_blocked.json": "review_chain_summary_packet_blocked_stale_decision",
        "stale_trend_blocked.json": "review_chain_summary_packet_blocked_stale_trend",
        "stale_request_blocked.json": "review_chain_summary_packet_blocked_stale_request",
        "stale_gate_blocked.json": "review_chain_summary_packet_blocked_stale_gate",
        "stale_deferral_blocked.json": "review_chain_summary_packet_blocked_stale_deferral",
        "media_payload_blocked.json": "review_chain_summary_packet_blocked_media_payload",
        "base64_payload_blocked.json": "review_chain_summary_packet_blocked_media_payload",
        "speaker_boundary_blocked.json": "review_chain_summary_packet_blocked_speaker_boundary",
        "external_authority_blocked.json": "review_chain_summary_packet_blocked_external_authority",
    }
    for fixture, status in expected.items():
        assert evaluate_review_chain_summary_packet(load(fixture)).status == status


def test_stale_and_mixed_scope_can_warn_by_policy() -> None:
    fixtures = ("stale_review_warning.json", "stale_decision_warning.json", "stale_trend_warning.json", "stale_request_warning.json", "stale_gate_warning.json", "stale_deferral_warning.json", "mixed_scope_diagnostic_warning.json")
    for fixture in fixtures:
        assert evaluate_review_chain_summary_packet(load(fixture)).status == "review_chain_summary_packet_ready_with_warnings"


def test_mixed_review_chain_summary_packet_counts_and_digest_are_deterministic() -> None:
    first = evaluate_review_chain_summary_packet(load("mixed_review_chain_summary_packet.json")).to_dict()
    second = evaluate_review_chain_summary_packet(load("mixed_review_chain_summary_packet.json")).to_dict()
    assert first == second
    assert first["packet"]["digest"]
    counts = first["report"]["summary_counts"]
    assert counts["stale_review_count"] == 1
    assert counts["stale_gate_count"] == 1
    assert counts["renewal_required_count"] >= 1
    assert counts["proof_refresh_required_count"] >= 1
    assert counts["future_live_deferred_count"] >= 3


def test_no_media_payloads_in_fixtures_except_boundary_tokens() -> None:
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "data:image" not in text
        assert "data:audio" not in text
        assert "data:video" not in text
        assert "real_hardware_serial" not in text


def test_no_live_camera_hardware_provider_network_subprocess_or_action_wing_calls() -> None:
    text = Path("sentientos/household_presence_camera_review_chain_summary_packet.py").read_text(encoding="utf-8")
    forbidden = ("/dev/video", "cv2", "OpenCV", "v4l2", "DirectShow", "AVFoundation", "MediaDevices", "OpenXR", "Quest", "requests.", "urllib", "subprocess", "camera_daemon", "vision_tracker", "face_emotion", "gaze_adapter", "talkback_bridge", "resident_kernel")
    for token in forbidden:
        assert token not in text
    assert "attempt_capture" in FORBIDDEN_NEXT_STEPS
