from __future__ import annotations

import copy
import hashlib
import json

import pytest

from sentientos.avatar_renderer_report_ingress import (
    RendererReportIngressError,
    renderer_report_observation,
    renderer_report_world_state_record,
)

pytestmark = pytest.mark.no_legacy_skip


def _report() -> dict[str, object]:
    report: dict[str, object] = {
        "schema_version": "sentientos.avatar_renderer_report:v1",
        "evidence_class": "avatar_renderer_reported_state",
        "source_id": "godot-procedural-demo",
        "renderer_generation_id": "godot-demo-12345",
        "sequence": 1,
        "reported_at": "2026-11-02T06:30:00Z",
        "session_id": "session-1",
        "turn_id": "turn-2",
        "output_digest": "a" * 64,
        "output_mode": "chat_response_visual_only",
        "commanded_state": {
            "expression": "smile", "mood": "joy", "intensity": 0.8,
            "motion": "wave", "workload_mode": "gaming",
        },
        "renderer_state": {
            "expression": {"status": "procedural_fallback_applied"},
            "motion": {
                "active_motion": "wave",
                "animation_player_active": False,
                "head_rotation_radians": {"x": 0.0, "y": 0.0, "z": 0.0},
                "left_arm_rotation_radians": {"x": 0.0, "y": 0.0, "z": -0.39},
                "body_position": {"x": 0.0, "y": 0.66, "z": 0.0},
                "observed_nodes": {"head": True, "left_arm": True, "body": True},
            },
            "applied_render_cap_fps": 15,
        },
        "frame_delta_seconds": 0.016,
        "apply_duration_usec": 500,
        "body_generation": "godot-procedural-demo-unadopted",
        "effect_proven": False,
        "independent_observation": False,
        "source_digest": "",
    }
    digest_payload = {key: value for key, value in report.items() if key != "source_digest"}
    report["source_digest"] = "sha256:" + hashlib.sha256(json.dumps(
        digest_payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    return report


def _refresh_digest(report: dict[str, object]) -> None:
    payload = {key: value for key, value in report.items() if key != "source_digest"}
    report["source_digest"] = "sha256:" + hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def test_renderer_report_projects_through_existing_owner_without_authority():
    record = renderer_report_world_state_record(_report())

    assert record["source_kind"] == "embodiment"
    assert record["evidence_strength"] == "unverified_caller_assertion"
    assert record["effect_proven"] is False
    assert record["payload"]["embodiment_evidence_class"] == "avatar_renderer_reported_state"
    assert record["payload"]["renderer_report"]["turn_id"] == "turn-2"
    assert record["payload"]["capture_status"] == "unverified_renderer_self_report"


@pytest.mark.parametrize("field,value", [
    ("effect_proven", True),
    ("independent_observation", True),
    ("source_id", "untrusted-renderer"),
    ("sequence", True),
])
def test_renderer_report_rejects_authority_masquerade_and_invalid_identity(field, value):
    report = _report()
    report[field] = value

    with pytest.raises(RendererReportIngressError):
        renderer_report_observation(report)


def test_renderer_report_rejects_incomplete_correlation_and_open_fields():
    incomplete = _report()
    incomplete["turn_id"] = None
    _refresh_digest(incomplete)
    extra = _report()
    extra["approval_grant"] = "must_not_cross_renderer_boundary"

    with pytest.raises(RendererReportIngressError, match="correlation_incomplete"):
        renderer_report_observation(incomplete)
    with pytest.raises(RendererReportIngressError, match="shape_invalid"):
        renderer_report_observation(extra)


def test_renderer_report_rejects_mismatched_self_report_digest():
    report = _report()
    report["source_digest"] = "sha256:" + "c" * 64

    with pytest.raises(RendererReportIngressError, match="source_digest_mismatch"):
        renderer_report_observation(report)


def test_renderer_report_digest_changes_when_report_changes():
    first = renderer_report_observation(_report())
    changed = copy.deepcopy(_report())
    changed["renderer_state"]["motion"]["active_motion"] = "idle"  # type: ignore[index]
    _refresh_digest(changed)
    second = renderer_report_observation(changed)

    assert first.source_digest != second.source_digest
