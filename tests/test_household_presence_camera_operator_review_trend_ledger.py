from __future__ import annotations

import json

import pytest
from pathlib import Path

from sentientos.household_presence_camera_operator_review_trend_ledger import (
    FORBIDDEN_NEXT_STEPS,
    build_default_policy,
    evaluate_operator_review_trend_ledger,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/household_presence_camera_operator_review_trend_ledger")


def load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def trend_types(name: str) -> set[str]:
    return {record.trend_type for record in evaluate_operator_review_trend_ledger(load(name)).ledger.records}


def test_default_policy_validates() -> None:
    assert validate_policy(build_default_policy()) == {"ok": True, "status": "household_presence_camera_operator_review_trend_ledger_policy_valid"}


def test_missing_and_invalid_decision_records_block() -> None:
    assert evaluate_operator_review_trend_ledger(load("missing_decision_records_blocked.json")).status == "operator_review_trend_ledger_blocked_missing_decision_records"
    assert evaluate_operator_review_trend_ledger(load("invalid_decision_record_blocked.json")).status == "operator_review_trend_ledger_blocked_invalid_decision_record"


def test_repeated_deny_defer_repair_and_renewal_trends_record_successfully() -> None:
    expected = {
        "valid_repeated_capture_denials.json": ("repeated_capture_denials", "sustain_capture_denial"),
        "valid_repeated_review_deferrals.json": ("repeated_review_deferrals", "operator_review_required"),
        "valid_operator_grant_renewal_trend.json": ("repeated_operator_grant_renewals", "renew_operator_grant"),
        "valid_dry_run_repair_trend.json": ("repeated_dry_run_repairs", "repair_dry_run_proof"),
        "valid_policy_chain_repair_trend.json": ("repeated_policy_chain_repairs", "repair_policy_chain_proof"),
        "valid_zone_config_repair_trend.json": ("repeated_zone_config_repairs", "repair_zone_config"),
        "valid_disabled_capture_boundary_repair_trend.json": ("repeated_disabled_capture_boundary_repairs", "repair_disabled_capture_boundary"),
    }
    for fixture, (trend, action) in expected.items():
        result = evaluate_operator_review_trend_ledger(load(fixture))
        assert result.status == "operator_review_trend_ledger_ready"
        assert result.ledger.records[0].trend_type == trend
        assert result.ledger.records[0].safe_next_action == action


def test_dry_run_continuation_and_future_live_deferral_never_enable_live_readiness() -> None:
    dry = evaluate_operator_review_trend_ledger(load("valid_dry_run_only_continuation_history.json")).ledger.records[0]
    future = evaluate_operator_review_trend_ledger(load("valid_future_live_review_deferred_history.json")).ledger.records[0]
    assert dry.trend_type == "dry_run_only_continuation_history"
    assert dry.safe_next_action == "continue_dry_run_only_review"
    assert future.trend_type == "future_live_review_deferred_history"
    assert future.safe_next_action == "defer_future_live_review"
    for record in (dry, future):
        assert record.trend_enables_live_capture is False
        assert record.trend_confers_operator_consent is False
        assert record.live_hardware_enabled is False


def test_stale_review_warns_or_blocks_by_policy() -> None:
    warn = evaluate_operator_review_trend_ledger(load("valid_stale_review_pattern_warn.json"))
    assert warn.status == "operator_review_trend_ledger_ready_with_warnings"
    assert "stale_review_pattern" in {record.trend_type for record in warn.ledger.records}
    blocked = evaluate_operator_review_trend_ledger(load("stale_review_pattern_blocked.json"))
    assert blocked.status == "operator_review_trend_ledger_invalid"


def test_scope_mismatch_blocks_by_default_and_mixed_scope_can_warn() -> None:
    assert evaluate_operator_review_trend_ledger(load("scope_mismatch_blocked.json")).status == "operator_review_trend_ledger_blocked_scope_mismatch"
    mixed = evaluate_operator_review_trend_ledger(load("mixed_operator_review_pattern_warn.json"))
    assert mixed.status == "operator_review_trend_ledger_ready_with_warnings"
    assert "mixed_operator_review_pattern" in {record.trend_type for record in mixed.ledger.records}


def test_media_speaker_and_external_authority_boundaries_block() -> None:
    expected = {
        "media_payload_blocked.json": "operator_review_trend_ledger_blocked_media_payload",
        "base64_payload_blocked.json": "operator_review_trend_ledger_blocked_media_payload",
        "speaker_boundary_blocked.json": "operator_review_trend_ledger_blocked_speaker_boundary",
        "external_authority_blocked.json": "operator_review_trend_ledger_blocked_external_authority",
    }
    for fixture, status in expected.items():
        assert evaluate_operator_review_trend_ledger(load(fixture)).status == status


def test_successful_outputs_pin_non_authority_flags_and_forbidden_steps() -> None:
    result = evaluate_operator_review_trend_ledger(load("valid_repeated_capture_denials.json"))
    record = result.ledger.records[0]
    assert record.capture_enabled is False
    assert record.capture_available is False
    assert record.live_hardware_enabled is False
    assert record.raw_media_storage_enabled is False
    assert record.no_live_capture_performed is True
    assert record.speaker_output_enabled is False
    assert record.external_disclosure_enabled is False
    assert record.trend_enables_live_capture is False
    assert record.trend_confers_operator_consent is False
    for step in ["attempt_capture", "enable_live_capture", "bypass_review_decision_ledger", "infer_operator_consent_from_trends", "convert_trend_to_live_readiness", "enable_external_disclosure"]:
        assert step in record.forbidden_next_steps
    assert set(FORBIDDEN_NEXT_STEPS).issubset(record.forbidden_next_steps)


def test_no_trend_detected_and_deterministic_digest_output() -> None:
    result = evaluate_operator_review_trend_ledger(load("no_trend_detected.json"))
    assert result.status == "operator_review_trend_ledger_ready"
    assert result.ledger.records[0].trend_type == "no_trend_detected"
    first = evaluate_operator_review_trend_ledger(load("mixed_trend_ledger.json")).to_dict()
    second = evaluate_operator_review_trend_ledger(load("mixed_trend_ledger.json")).to_dict()
    assert first == second
    assert first["ledger"]["digest"]


def test_mixed_trend_ledger_counts_and_digest_are_deterministic() -> None:
    result = evaluate_operator_review_trend_ledger(load("mixed_trend_ledger.json"))
    assert result.report.summary_counts["total_decision_count"] == 10
    assert "mixed_operator_review_pattern" in trend_types("mixed_trend_ledger.json")
    assert len(result.ledger.digest) == 64


def test_fixtures_are_metadata_only() -> None:
    forbidden = ["media_payload", "base64_media", "base64_payload", "image_payload", "video_payload", "audio_payload", "thumbnail", "screenshot", "raw_transcript", "hardware_serial"]
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        if path.name in {"media_payload_blocked.json", "base64_payload_blocked.json"}:
            continue
        assert not any(token in text for token in forbidden), path


def test_library_has_no_live_hardware_provider_network_subprocess_or_action_wing_calls() -> None:
    text = Path("sentientos/household_presence_camera_operator_review_trend_ledger.py").read_text(encoding="utf-8")
    forbidden = ["import subprocess", "opencv", "import cv2", "/dev/video", "directshow", "avfoundation", "mediadevices", "openxr", "meta quest", "import requests", "urllib", "github", "camera_daemon", "vision_tracker", "face_emotion", "gaze_adapter", "talkback_bridge", "resident_kernel", "action_wing"]
    assert not any(token in text.lower() for token in forbidden)
