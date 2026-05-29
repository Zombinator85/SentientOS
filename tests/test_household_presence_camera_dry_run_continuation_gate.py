from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.household_presence_camera_dry_run_continuation_gate import (
    FORBIDDEN_NEXT_STEPS,
    build_default_policy,
    evaluate_dry_run_continuation_gate,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/household_presence_camera_dry_run_continuation_gate")
FALSE_FLAGS = (
    "capture_enabled",
    "capture_available",
    "live_hardware_enabled",
    "raw_media_storage_enabled",
    "speaker_output_enabled",
    "external_disclosure_enabled",
    "gate_grants_operator_consent",
    "gate_renews_operator_grant",
    "gate_enables_live_capture",
    "gate_enables_live_hardware",
    "gate_enables_raw_media_storage",
    "gate_enables_speaker_output",
    "gate_enables_external_disclosure",
    "gate_confers_live_readiness",
    "gate_confers_capture_authorization",
    "gate_executes_dry_run",
)


def load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_validates() -> None:
    assert validate_policy(build_default_policy()) == {"ok": True, "status": "household_presence_camera_dry_run_continuation_gate_policy_valid"}


def test_valid_dry_run_only_continuation_is_metadata_ready_without_execution() -> None:
    result = evaluate_dry_run_continuation_gate(load("valid_continue_dry_run_only_review.json"))
    assert result.status == "dry_run_continuation_gate_ready"
    assert result.gate is not None
    assert result.gate.gate_decision == "continue_dry_run_only"
    assert result.gate.safe_next_action == "continue_dry_run_only_review"
    assert result.gate.no_live_capture_performed is True
    assert all(getattr(result.gate, flag) is False for flag in FALSE_FLAGS)
    assert set(("attempt_capture", "enable_live_capture", "bypass_operator_grant_renewal_request_packet", "infer_operator_consent_from_gate", "convert_dry_run_gate_to_live_readiness", "convert_dry_run_gate_to_live_capture_permission", "enable_external_disclosure")).issubset(result.gate.forbidden_next_steps)


def test_missing_required_upstream_evidence_blocks() -> None:
    expected = {
        "missing_review_packet_blocked.json": "dry_run_continuation_gate_blocked_missing_review_packet",
        "missing_decision_ledger_blocked.json": "dry_run_continuation_gate_blocked_missing_decision_ledger",
        "missing_trend_ledger_blocked.json": "dry_run_continuation_gate_blocked_missing_trend_ledger",
        "missing_renewal_request_packet_blocked.json": "dry_run_continuation_gate_blocked_missing_renewal_request_packet",
    }
    for fixture, status in expected.items():
        assert evaluate_dry_run_continuation_gate(load(fixture)).status == status


def test_not_ready_upstream_evidence_blocks() -> None:
    expected = {
        "review_packet_not_ready_blocked.json": "dry_run_continuation_gate_blocked_review_packet_not_ready",
        "decision_ledger_not_ready_blocked.json": "dry_run_continuation_gate_blocked_decision_ledger_not_ready",
        "trend_ledger_not_ready_blocked.json": "dry_run_continuation_gate_blocked_trend_ledger_not_ready",
        "renewal_request_not_ready_blocked.json": "dry_run_continuation_gate_blocked_renewal_request_not_ready",
    }
    for fixture, status in expected.items():
        assert evaluate_dry_run_continuation_gate(load(fixture)).status == status


def test_ready_with_warnings_continuation_warns_when_policy_permits() -> None:
    result = evaluate_dry_run_continuation_gate(load("valid_continue_with_warnings.json"))
    assert result.status == "dry_run_continuation_gate_ready_with_warnings"
    assert result.gate is not None
    assert result.gate.stale_trend_count == 1


def test_operator_review_and_future_live_deferral_are_not_live_readiness() -> None:
    review = evaluate_dry_run_continuation_gate(load("valid_operator_review_required.json"))
    assert review.status == "dry_run_continuation_gate_ready_with_warnings"
    assert review.gate is not None
    assert review.gate.gate_decision == "require_operator_review"
    future = evaluate_dry_run_continuation_gate(load("future_live_deferred_context.json"))
    assert future.status == "dry_run_continuation_gate_ready_with_warnings"
    assert future.gate is not None
    assert future.gate.gate_decision == "defer_future_live_review"
    assert future.gate.gate_confers_live_readiness is False


def test_renewal_and_proof_refresh_requirements_block_by_default() -> None:
    expected = {
        "operator_grant_renewal_required_blocked.json": "dry_run_continuation_gate_blocked_operator_grant_required",
        "dry_run_proof_refresh_required_blocked.json": "dry_run_continuation_gate_blocked_proof_refresh_required",
        "policy_chain_refresh_required_blocked.json": "dry_run_continuation_gate_blocked_proof_refresh_required",
        "zone_config_refresh_required_blocked.json": "dry_run_continuation_gate_blocked_proof_refresh_required",
        "disabled_capture_boundary_refresh_required_blocked.json": "dry_run_continuation_gate_blocked_proof_refresh_required",
        "capture_review_packet_rerun_required_blocked.json": "dry_run_continuation_gate_blocked_proof_refresh_required",
        "decision_ledger_review_required_blocked.json": "dry_run_continuation_gate_blocked_proof_refresh_required",
        "trend_ledger_review_required_blocked.json": "dry_run_continuation_gate_blocked_proof_refresh_required",
        "renewal_request_review_required_blocked.json": "dry_run_continuation_gate_blocked_proof_refresh_required",
    }
    for fixture, status in expected.items():
        assert evaluate_dry_run_continuation_gate(load(fixture)).status == status


def test_denials_stale_scope_media_speaker_external_boundaries() -> None:
    expected = {
        "sustain_capture_denial_blocked.json": "dry_run_continuation_gate_blocked_unresolved_denials",
        "unresolved_denials_blocked.json": "dry_run_continuation_gate_blocked_unresolved_denials",
        "scope_mismatch_blocked.json": "dry_run_continuation_gate_blocked_scope_mismatch",
        "stale_review_blocked.json": "dry_run_continuation_gate_blocked_stale_review",
        "media_payload_blocked.json": "dry_run_continuation_gate_blocked_media_payload",
        "base64_payload_blocked.json": "dry_run_continuation_gate_blocked_media_payload",
        "speaker_boundary_blocked.json": "dry_run_continuation_gate_blocked_speaker_boundary",
        "external_authority_blocked.json": "dry_run_continuation_gate_blocked_external_authority",
    }
    for fixture, status in expected.items():
        assert evaluate_dry_run_continuation_gate(load(fixture)).status == status


def test_stale_trend_request_and_mixed_scope_can_warn_by_policy() -> None:
    for fixture in ("stale_trend_warning.json", "stale_request_warning.json", "mixed_scope_diagnostic_warning.json"):
        assert evaluate_dry_run_continuation_gate(load(fixture)).status == "dry_run_continuation_gate_ready_with_warnings"


def test_mixed_gate_packet_counts_and_digest_are_deterministic() -> None:
    first = evaluate_dry_run_continuation_gate(load("mixed_gate_packet.json")).to_dict()
    second = evaluate_dry_run_continuation_gate(load("mixed_gate_packet.json")).to_dict()
    assert first == second
    assert first["gate"]["digest"]
    assert first["report"]["summary_counts"]["future_live_deferred_count"] == 1
    assert first["report"]["summary_counts"]["stale_trend_count"] == 1
    assert first["report"]["summary_counts"]["stale_request_count"] == 1


def test_no_media_payloads_in_fixtures_except_boundary_tokens() -> None:
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "data:image" not in text
        assert "data:audio" not in text
        assert "data:video" not in text
        assert "real_hardware_serial" not in text


def test_no_live_camera_hardware_provider_network_subprocess_or_action_wing_calls() -> None:
    text = Path("sentientos/household_presence_camera_dry_run_continuation_gate.py").read_text(encoding="utf-8")
    forbidden = ("/dev/video", "cv2", "OpenCV", "v4l2", "DirectShow", "AVFoundation", "MediaDevices", "OpenXR", "Quest", "subprocess", "requests.", "urllib", "github", "camera_daemon", "vision_tracker", "face_emotion", "gaze_adapter", "talkback_bridge", "resident_kernel")
    for token in forbidden:
        assert token not in text
    assert "attempt_capture" in FORBIDDEN_NEXT_STEPS
