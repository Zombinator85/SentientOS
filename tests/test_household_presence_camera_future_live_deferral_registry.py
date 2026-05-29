from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.household_presence_camera_future_live_deferral_registry import (
    FORBIDDEN_NEXT_STEPS,
    build_default_policy,
    evaluate_future_live_deferral_registry,
    validate_policy,
)

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/household_presence_camera_future_live_deferral_registry")
FALSE_FLAGS = (
    "capture_enabled",
    "capture_available",
    "live_hardware_enabled",
    "raw_media_storage_enabled",
    "speaker_output_enabled",
    "external_disclosure_enabled",
    "deferral_grants_operator_consent",
    "deferral_renews_operator_grant",
    "deferral_enables_live_capture",
    "deferral_enables_live_hardware",
    "deferral_enables_raw_media_storage",
    "deferral_enables_speaker_output",
    "deferral_enables_external_disclosure",
    "deferral_confers_live_readiness",
    "deferral_confers_capture_authorization",
    "deferral_schedules_live_review",
    "deferral_approves_live_candidate",
    "deferral_executes_dry_run",
)


def load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_default_policy_validates() -> None:
    assert validate_policy(build_default_policy()) == {"ok": True, "status": "household_presence_camera_future_live_deferral_registry_policy_valid"}


def test_missing_required_upstream_evidence_blocks() -> None:
    expected = {
        "missing_dry_run_gate_blocked.json": "future_live_deferral_registry_blocked_missing_dry_run_gate",
        "missing_renewal_request_packet_blocked.json": "future_live_deferral_registry_blocked_missing_renewal_request_packet",
        "missing_trend_ledger_blocked.json": "future_live_deferral_registry_blocked_missing_trend_ledger",
        "missing_decision_ledger_blocked.json": "future_live_deferral_registry_blocked_missing_decision_ledger",
        "missing_review_packet_blocked.json": "future_live_deferral_registry_blocked_missing_review_packet",
    }
    for fixture, status in expected.items():
        assert evaluate_future_live_deferral_registry(load(fixture)).status == status


def test_not_ready_dry_run_gate_blocks() -> None:
    assert evaluate_future_live_deferral_registry(load("dry_run_gate_not_ready_blocked.json")).status == "future_live_deferral_registry_blocked_dry_run_gate_not_ready"


def test_valid_future_live_deferral_records_metadata_only_boundaries() -> None:
    result = evaluate_future_live_deferral_registry(load("valid_future_live_review_deferred.json"))
    assert result.status == "future_live_deferral_registry_ready"
    assert result.registry is not None
    record = result.registry.records[0]
    assert record.deferral_type == "future_live_review_deferred"
    assert record.safe_next_action == "maintain_future_live_deferral"
    assert record.no_live_capture_performed is True
    assert all(getattr(record, flag) is False for flag in FALSE_FLAGS)
    assert set(("attempt_capture", "enable_live_capture", "schedule_live_capture_review", "approve_live_candidate", "mark_live_ready", "bypass_dry_run_continuation_gate", "infer_operator_consent_from_deferral", "convert_deferral_to_live_readiness", "convert_deferral_to_live_capture_permission", "enable_external_disclosure")).issubset(record.forbidden_next_steps)


def test_context_types_are_not_consent_or_live_readiness() -> None:
    expected = {
        "valid_dry_run_continuation_not_live_readiness.json": ("dry_run_continuation_not_live_readiness", "inspect_dry_run_gate"),
        "valid_grant_renewal_request_not_live_consent.json": ("grant_renewal_request_not_live_consent", "inspect_renewal_request"),
        "valid_trend_history_not_live_consent.json": ("trend_history_not_live_consent", "inspect_trend_history"),
        "valid_decision_history_not_live_consent.json": ("decision_history_not_live_consent", "inspect_decision_history"),
        "valid_live_candidate_review_not_requested.json": ("live_candidate_review_not_requested", "maintain_future_live_deferral"),
        "valid_requires_separate_operator_confirmation.json": ("live_candidate_review_requires_separate_operator_confirmation", "maintain_future_live_deferral"),
    }
    for fixture, (deferral_type, action) in expected.items():
        result = evaluate_future_live_deferral_registry(load(fixture))
        assert result.status == "future_live_deferral_registry_ready"
        assert result.registry is not None
        record = result.registry.records[0]
        assert record.deferral_type == deferral_type
        assert record.safe_next_action == action
        assert record.deferral_confers_live_readiness is False
        assert record.deferral_grants_operator_consent is False


def test_unsafe_live_implications_operator_grant_and_proof_refresh_behaviors() -> None:
    assert evaluate_future_live_deferral_registry(load("unsafe_live_implication_blocked.json")).status == "future_live_deferral_registry_blocked_unsafe_live_implication"
    grant = evaluate_future_live_deferral_registry(load("valid_operator_grant_required_deferral.json"))
    assert grant.status == "future_live_deferral_registry_ready_with_warnings"
    assert grant.registry is not None
    assert grant.registry.records[0].deferral_type == "operator_grant_required_before_future_live_review"
    proof = evaluate_future_live_deferral_registry(load("valid_proof_refresh_required_deferral.json"))
    assert proof.status == "future_live_deferral_registry_ready_with_warnings"
    assert proof.registry is not None
    assert proof.registry.records[0].deferral_type == "proof_refresh_required_before_future_live_review"


def test_denials_scope_stale_media_speaker_external_boundaries() -> None:
    expected = {
        "unresolved_denials_blocked.json": "future_live_deferral_registry_blocked_unresolved_denials",
        "scope_mismatch_blocked.json": "future_live_deferral_registry_blocked_scope_mismatch",
        "stale_gate_blocked.json": "future_live_deferral_registry_blocked_stale_gate",
        "stale_request_blocked.json": "future_live_deferral_registry_blocked_stale_request",
        "stale_trend_blocked.json": "future_live_deferral_registry_blocked_stale_trend",
        "stale_review_blocked.json": "future_live_deferral_registry_blocked_stale_review",
        "media_payload_blocked.json": "future_live_deferral_registry_blocked_media_payload",
        "base64_payload_blocked.json": "future_live_deferral_registry_blocked_media_payload",
        "speaker_boundary_blocked.json": "future_live_deferral_registry_blocked_speaker_boundary",
        "external_authority_blocked.json": "future_live_deferral_registry_blocked_external_authority",
    }
    for fixture, status in expected.items():
        assert evaluate_future_live_deferral_registry(load(fixture)).status == status


def test_stale_and_mixed_scope_can_warn_by_policy() -> None:
    for fixture in ("valid_stale_gate_warning.json", "valid_stale_request_warning.json", "valid_stale_trend_warning.json", "valid_stale_review_warning.json", "valid_mixed_scope_diagnostic_warning.json"):
        assert evaluate_future_live_deferral_registry(load(fixture)).status == "future_live_deferral_registry_ready_with_warnings"


def test_mixed_deferral_registry_counts_and_digest_are_deterministic() -> None:
    first = evaluate_future_live_deferral_registry(load("mixed_deferral_registry.json")).to_dict()
    second = evaluate_future_live_deferral_registry(load("mixed_deferral_registry.json")).to_dict()
    assert first == second
    assert first["registry"]["digest"]
    assert first["report"]["summary_counts"]["future_live_deferred_count"] == 1
    assert first["report"]["summary_counts"]["stale_gate_count"] == 1
    assert first["report"]["summary_counts"]["stale_trend_count"] == 1


def test_no_media_payloads_in_fixtures_except_boundary_tokens() -> None:
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "data:image" not in text
        assert "data:audio" not in text
        assert "data:video" not in text
        assert "real_hardware_serial" not in text


def test_no_live_camera_hardware_provider_network_or_action_wing_calls() -> None:
    text = Path("sentientos/household_presence_camera_future_live_deferral_registry.py").read_text(encoding="utf-8")
    forbidden = ("/dev/video", "cv2", "OpenCV", "v4l2", "DirectShow", "AVFoundation", "MediaDevices", "OpenXR", "Quest", "requests.", "urllib", "camera_daemon", "vision_tracker", "face_emotion", "gaze_adapter", "talkback_bridge", "resident_kernel")
    for token in forbidden:
        assert token not in text
    assert "attempt_capture" in FORBIDDEN_NEXT_STEPS
