from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sentientos.household_presence_camera_operator_grant_renewal_request_packet import (
    FORBIDDEN_NEXT_STEPS,
    HouseholdCameraOperatorGrantRenewalRequestPolicy,
    build_default_policy,
    evaluate_operator_grant_renewal_request_packet,
    validate_policy,
)

FIXTURES = Path("tests/fixtures/household_presence_camera_operator_grant_renewal_request_packet")


def load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def first(name: str):
    result = evaluate_operator_grant_renewal_request_packet(load(name))
    assert result.status in {"operator_grant_renewal_request_packet_ready", "operator_grant_renewal_request_packet_ready_with_warnings"}
    return result.packet.records[0]


def test_default_policy_validates() -> None:
    assert validate_policy(build_default_policy())["status"] == "household_presence_camera_operator_grant_renewal_request_packet_policy_valid"


def test_required_inputs_block_by_default() -> None:
    expected = {
        "missing_trend_ledger_blocked.json": "operator_grant_renewal_request_packet_blocked_missing_trend_ledger",
        "missing_decision_ledger_blocked.json": "operator_grant_renewal_request_packet_blocked_missing_decision_ledger",
        "missing_review_packet_blocked.json": "operator_grant_renewal_request_packet_blocked_missing_review_packet",
        "invalid_trend_record_blocked.json": "operator_grant_renewal_request_packet_blocked_invalid_trend_record",
        "noop_request_blocked.json": "operator_grant_renewal_request_packet_blocked_no_renewal_pressure",
    }
    for fixture, status in expected.items():
        assert evaluate_operator_grant_renewal_request_packet(load(fixture)).status == status


def test_operator_grant_renewal_request_is_not_consent_or_grant() -> None:
    record = first("valid_operator_grant_renewal_request.json")
    assert record.request_reason == "repeated_operator_grant_renewal_pressure"
    assert record.requested_refresh_types == ("operator_grant_renewal",)
    assert record.safe_next_action == "request_operator_grant_renewal"
    assert record.request_grants_operator_consent is False
    assert record.request_renews_operator_grant is False


def test_proof_repair_trends_map_to_matching_refreshes() -> None:
    cases = {
        "valid_dry_run_proof_refresh_request.json": ("dry_run_proof_refresh", "request_dry_run_proof_refresh"),
        "valid_policy_chain_proof_refresh_request.json": ("policy_chain_proof_refresh", "request_policy_chain_proof_refresh"),
        "valid_zone_config_refresh_request.json": ("zone_config_refresh", "request_zone_config_refresh"),
        "valid_disabled_capture_boundary_refresh_request.json": ("disabled_capture_boundary_refresh", "request_disabled_capture_boundary_refresh"),
    }
    for fixture, (refresh, action) in cases.items():
        record = first(fixture)
        assert record.requested_refresh_types == (refresh,)
        assert record.safe_next_action == action


def test_denial_stale_dry_run_and_future_live_behaviors() -> None:
    assert first("valid_denial_history_review_request.json").safe_next_action == "sustain_capture_denial"
    assert first("valid_stale_review_refresh_request.json").requested_refresh_types == ("capture_review_packet_rerun",)
    assert first("valid_stale_trend_refresh_request.json").requested_refresh_types in [("operator_grant_renewal",), ("trend_ledger_review",)]
    dry = first("valid_dry_run_continuation_review_request.json")
    assert dry.request_enables_dry_run_continuation is False
    future = first("valid_future_live_deferral_confirmation_request.json")
    assert future.safe_next_action == "defer_future_live_review"
    assert future.request_confers_live_readiness is False


def test_scope_trend_only_stale_and_boundaries() -> None:
    assert evaluate_operator_grant_renewal_request_packet(load("scope_mismatch_blocked.json")).status == "operator_grant_renewal_request_packet_blocked_scope_mismatch"
    mixed = evaluate_operator_grant_renewal_request_packet(load("valid_mixed_scope_diagnostic_warning.json"))
    assert mixed.status == "operator_grant_renewal_request_packet_ready_with_warnings"
    trend_only = evaluate_operator_grant_renewal_request_packet(load("valid_trend_only_diagnostic_warning.json"))
    assert trend_only.status == "operator_grant_renewal_request_packet_ready_with_warnings"
    assert evaluate_operator_grant_renewal_request_packet(load("stale_trend_blocked.json")).status == "operator_grant_renewal_request_packet_blocked_stale_trend"
    assert evaluate_operator_grant_renewal_request_packet(load("stale_review_blocked.json")).status == "operator_grant_renewal_request_packet_blocked_stale_trend"
    expected = {
        "media_payload_blocked.json": "operator_grant_renewal_request_packet_blocked_media_payload",
        "base64_payload_blocked.json": "operator_grant_renewal_request_packet_blocked_media_payload",
        "speaker_boundary_blocked.json": "operator_grant_renewal_request_packet_blocked_speaker_boundary",
        "external_authority_blocked.json": "operator_grant_renewal_request_packet_blocked_external_authority",
    }
    for fixture, status in expected.items():
        assert evaluate_operator_grant_renewal_request_packet(load(fixture)).status == status


def test_success_outputs_explicit_false_boundaries_and_forbidden_steps() -> None:
    record = first("valid_operator_grant_renewal_request.json")
    for attr in (
        "capture_enabled",
        "capture_available",
        "live_hardware_enabled",
        "raw_media_storage_enabled",
        "speaker_output_enabled",
        "external_disclosure_enabled",
        "request_grants_operator_consent",
        "request_renews_operator_grant",
        "request_enables_live_capture",
        "request_enables_dry_run_continuation",
        "request_confers_live_readiness",
    ):
        assert getattr(record, attr) is False
    assert record.no_live_capture_performed is True
    for forbidden in ("attempt_capture", "enable_live_capture", "bypass_operator_review_trend_ledger", "infer_operator_consent_from_renewal_request", "convert_renewal_request_to_grant", "convert_renewal_request_to_live_readiness", "enable_external_disclosure"):
        assert forbidden in record.forbidden_next_steps
    assert record.forbidden_next_steps == FORBIDDEN_NEXT_STEPS


def test_deterministic_json_digest_and_mixed_counts() -> None:
    first_result = evaluate_operator_grant_renewal_request_packet(load("mixed_request_packet.json")).to_dict()
    second_result = evaluate_operator_grant_renewal_request_packet(load("mixed_request_packet.json")).to_dict()
    assert first_result == second_result
    assert len(first_result["packet"]["digest"]) == 64
    assert first_result["report"]["summary_counts"]["record_count"] == 3


def test_no_media_payloads_in_success_fixtures_and_no_live_import_strings() -> None:
    forbidden = ("/dev/video", "cv2", "OpenCV", "MediaDevices", "DirectShow", "AVFoundation", "OpenXR", "Quest", "camera_daemon", "vision_tracker", "face_emotion", "gaze_adapter", "talkback_bridge", "resident_kernel")
    text = Path("sentientos/household_presence_camera_operator_grant_renewal_request_packet.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert all(item not in text for item in forbidden)
    for path in FIXTURES.glob("valid*.json"):
        content = path.read_text(encoding="utf-8").lower()
        assert "base64" not in content
        assert "raw_media" not in content
        assert "thumbnail" not in content
        assert "screenshot" not in content
