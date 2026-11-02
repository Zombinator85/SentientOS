from __future__ import annotations

import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.avatar_renderer_report_ingress import (
    RendererReportIngressError,
    RendererReportCaptureOwner,
    RendererReportEvidenceStore,
    renderer_report_observation,
    renderer_report_world_state_record,
)
from sentientos.gaming_companion_bridge import CompanionBridgeReceiver, encode_message
from sentientos.gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
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


def test_authenticated_renderer_report_returns_to_durable_unverified_world_state(tmp_path: Path):
    now = datetime.now(timezone.utc).isoformat()
    report = _report()
    report["reported_at"] = now
    _refresh_digest(report)
    source_key, acknowledgment_key = b"r" * 32, b"a" * 32
    receiver = CompanionBridgeReceiver(source_keys={"windows-renderer-relay": source_key},
        expected_generations={"windows-renderer-relay": "edge-generation-12345"})
    runtime = CompanionBridgeLoopbackRuntime(receiver=receiver,
        acknowledgment_source_id="sentientos-core",
        acknowledgment_generation_id="core-generation-1",
        acknowledgment_key=acknowledgment_key)
    store = RendererReportEvidenceStore(tmp_path / "renderer-captures")
    owner = RendererReportCaptureOwner(runtime=runtime, store=store)
    owner.start()
    try:
        port = runtime.status().port
        assert port is not None
        ack_receiver = CompanionBridgeReceiver(source_keys={"sentientos-core": acknowledgment_key},
            expected_generations={"sentientos-core": "core-generation-1"})
        client = CompanionBridgeLoopbackClient(port=port, acknowledgment_receiver=ack_receiver)
        encoded = encode_message(kind="renderer_report", source_id="windows-renderer-relay",
            session_id="session-1", generation_id="edge-generation-12345", sequence=1,
            payload=report, key=source_key, created_at=now)
        acknowledgment = client.send(encoded)
        assert acknowledgment.payload["disposition"] == "accepted"
        deadline = time.monotonic() + 1.0
        while owner.status()["captured"] == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert owner.status()["captured"] == 1
        assert owner.status()["renderer_reports_are_independent_observations"] is False
        records = store.world_state_records()
        assert len(records) == 1
        record = records[0]
        assert record["effect_claimed"] is False and record["effect_proven"] is False
        assert record["payload"]["capture_status"] == "unverified_renderer_self_report"
        assert record["payload"]["transport_authenticated_at_capture"] is True
        assert record["payload"]["transport_authentication_principal"] == "windows-renderer-relay"
        assert record["payload"]["renderer_source_independently_authenticated"] is False
        assert record["payload"]["transport_signature_reverified_on_load"] is False
        assert record["payload"]["renderer_state_independently_observed"] is False
        captures = list((tmp_path / "renderer-captures").glob("*.json"))
        assert len(captures) == 1 and captures[0].stat().st_mode & 0o077 == 0
        archived = json.loads(captures[0].read_text(encoding="utf-8"))
        archived["transport_provenance"]["source_id"] = "forged-relay"
        tampered = json.dumps(archived, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
        replacement = captures[0].with_name(hashlib.sha256(tampered).hexdigest() + ".json")
        replacement.write_bytes(tampered)
        replacement.chmod(0o600)
        captures[0].unlink()
        assert store.world_state_records() == []
    finally:
        owner.close()


def test_renderer_capture_rejects_transport_lineage_mismatch_and_open_store(tmp_path: Path):
    store = RendererReportEvidenceStore(tmp_path / "private")
    with pytest.raises(RendererReportIngressError, match="lineage_mismatch"):
        store.capture(report=_report(), transport={
            "message_id": "a" * 64, "source_id": "godot-procedural-demo",
            "session_id": "session-1", "generation_id": "wrong-generation",
            "sequence": 1, "created_at": "2026-11-02T06:30:00Z",
            "report_source_id": "godot-procedural-demo",
            "report_generation_id": "wrong-generation", "report_sequence": 1,
            "signed_envelope": b"placeholder"})
    open_root = tmp_path / "open"
    open_root.mkdir(mode=0o755)
    open_root.chmod(0o755)
    with pytest.raises(RendererReportIngressError, match="permissions_too_open"):
        RendererReportEvidenceStore(open_root)


def test_renderer_report_v2_requires_truthful_speech_boundary_evidence():
    report = _report()
    report["schema_version"] = "sentientos.avatar_renderer_report:v2"
    report["renderer_state"]["speech"] = {"status": "speaking",
        "mouth_shape": "MouthOpen", "mouth_weight": 0.38,
        "timing_event": "word_started", "timing_source": "governed_local_tts",
        "phoneme_claimed": False}
    _refresh_digest(report)
    observation = renderer_report_observation(report)
    assert observation.source_schema == "sentientos.avatar_renderer_report:v2"
    assert observation.payload["renderer_report"]["renderer_state"]["speech"][
        "phoneme_claimed"] is False

    forged = copy.deepcopy(report)
    forged["renderer_state"]["speech"]["phoneme_claimed"] = True
    _refresh_digest(forged)
    with pytest.raises(RendererReportIngressError, match="speech_state_invalid"):
        renderer_report_observation(forged)
