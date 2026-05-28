from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.household_presence_camera_capture_review_decision_ledger import (
    FORBIDDEN_NEXT_STEPS,
    build_default_policy,
    evaluate_capture_review_decision_ledger,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/household_presence_camera_capture_review_decision_ledger")
SUCCESS_FIXTURES = [
    "valid_deny_decision.json",
    "valid_defer_decision.json",
    "valid_operator_grant_renewal_decision.json",
    "valid_dry_run_repair_decision.json",
    "valid_policy_chain_repair_decision.json",
    "valid_zone_config_repair_decision.json",
    "valid_disabled_capture_boundary_repair_decision.json",
    "valid_dry_run_only_continuation.json",
    "future_live_review_deferred.json",
    "sustain_denial_history.json",
    "reject_review_packet.json",
]


def load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_validates() -> None:
    assert validate_policy(build_default_policy()) == {
        "ok": True,
        "status": "household_presence_camera_capture_review_decision_ledger_policy_valid",
    }


@pytest.mark.parametrize("fixture", SUCCESS_FIXTURES)
def test_safe_decisions_record_without_enabling_capture(fixture: str) -> None:
    result = evaluate_capture_review_decision_ledger(load(fixture))
    assert result.status == "capture_review_decision_ledger_ready"
    record = result.ledger.records[0]
    assert record.capture_enabled is False
    assert record.capture_available is False
    assert record.live_hardware_enabled is False
    assert record.raw_media_storage_enabled is False
    assert record.no_live_capture_performed is True
    assert record.speaker_output_enabled is False
    assert record.external_disclosure_enabled is False
    for step in ["attempt_capture", "enable_live_capture", "bypass_review_packet", "bypass_denial_ledger", "enable_external_disclosure"]:
        assert step in record.forbidden_next_steps


def test_dry_run_only_continuation_requires_ready_review_packet() -> None:
    assert evaluate_capture_review_decision_ledger(load("valid_dry_run_only_continuation.json")).ledger.records[0].safe_next_action == "continue_dry_run_only"
    blocked = evaluate_capture_review_decision_ledger(load("review_packet_not_ready_blocked.json"))
    assert blocked.status == "capture_review_decision_ledger_blocked_review_packet_not_ready"


def test_future_live_review_remains_deferred() -> None:
    result = evaluate_capture_review_decision_ledger(load("future_live_review_deferred.json"))
    record = result.ledger.records[0]
    assert record.safe_next_action == "defer_future_live_review"
    assert record.capture_enabled is False
    assert record.live_hardware_enabled is False


@pytest.mark.parametrize(
    ("fixture", "status"),
    [
        ("missing_review_packet_blocked.json", "capture_review_decision_ledger_blocked_missing_review_packet"),
        ("unresolved_denials_blocked.json", "capture_review_decision_ledger_blocked_unresolved_denials"),
        ("scope_mismatch_blocked.json", "capture_review_decision_ledger_blocked_scope_mismatch"),
        ("stale_review_blocked.json", "capture_review_decision_ledger_blocked_stale_review"),
        ("media_payload_blocked.json", "capture_review_decision_ledger_blocked_media_payload"),
        ("base64_payload_blocked.json", "capture_review_decision_ledger_blocked_media_payload"),
        ("speaker_boundary_blocked.json", "capture_review_decision_ledger_blocked_speaker_boundary"),
        ("external_authority_blocked.json", "capture_review_decision_ledger_blocked_external_authority"),
    ],
)
def test_blocking_conditions(fixture: str, status: str) -> None:
    assert evaluate_capture_review_decision_ledger(load(fixture)).status == status


def test_stale_review_can_warn_by_policy() -> None:
    result = evaluate_capture_review_decision_ledger(load("valid_with_warnings.json"))
    assert result.status == "capture_review_decision_ledger_ready_with_warnings"
    assert [f.code for f in result.report.findings] == ["stale_review"]


def test_deterministic_json_digest_and_mixed_counts() -> None:
    payload = load("mixed_decision_ledger.json")
    first = evaluate_capture_review_decision_ledger(payload).to_dict()
    second = evaluate_capture_review_decision_ledger(payload).to_dict()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["ledger"]["digest"] == second["ledger"]["digest"]
    assert first["report"]["summary_counts"] == {
        "allow_dry_run_only_continuation": 1,
        "defer_review": 1,
        "deny_capture_request": 1,
        "mark_future_live_review_deferred": 1,
    }


def test_fixtures_are_metadata_only() -> None:
    forbidden = {"image", "video", "audio", "thumbnail", "screenshot", "raw_transcript", "real_serial"}
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text
        if path.name != "base64_payload_blocked.json":
            assert "base64" not in text


def test_library_does_not_import_live_hardware_or_action_surfaces() -> None:
    text = Path("sentientos/household_presence_camera_capture_review_decision_ledger.py").read_text(encoding="utf-8")
    forbidden = ["cv2", "/dev/video", "v4l2", "directshow", "avfoundation", "mediadevices", "openxr", "subprocess", "requests", "urllib", "github", "camera_daemon", "vision_tracker", "face_emotion", "gaze_adapter", "talkback_bridge", "resident_kernel"]
    lowered = text.lower()
    for token in forbidden:
        assert token not in lowered
    assert "enable_external_disclosure" in FORBIDDEN_NEXT_STEPS
