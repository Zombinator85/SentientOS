from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sentientosd import RuntimeMaintenanceSurfaces

from sentientos.avatar_renderer_report_ingress import (
    RendererReportIngressError,
    RendererReportCaptureOwner,
    RendererReportEvidenceStore,
    renderer_report_observation,
    renderer_report_receipt_identity,
    renderer_report_world_state_record,
    verify_renderer_report_receipt_identity,
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


def _adopted_body_report() -> dict[str, object]:
    report = _report()
    report["schema_version"] = "sentientos.avatar_renderer_report:v2"
    report["source_id"] = "godot-adopted-body-demo"
    report["body_identity"] = "companion-avatar-v4"
    report["body_generation"] = 4
    renderer_state = report["renderer_state"]
    assert isinstance(renderer_state, dict)
    renderer_state["speech"] = {"status": "not_requested", "phoneme_claimed": False}
    renderer_state["adopted_body"] = {
        "status": "active",
        "evidence_posture": "trusted_loader_adoption_receipt_verified",
        "artifact_sha256": "a" * 64,
        "manifest_digest": "sha256:" + "b" * 64,
        "pointer_digest": "sha256:" + "c" * 64,
        "adoption_receipt_digest": "sha256:" + "d" * 64,
        "authority_effects_performed": False,
    }
    _refresh_digest(report)
    return report


def test_renderer_report_projects_through_existing_owner_without_authority():
    record = renderer_report_world_state_record(_report())

    assert record["source_kind"] == "embodiment"
    assert record["evidence_strength"] == "unverified_caller_assertion"
    assert record["effect_proven"] is False
    assert record["payload"]["embodiment_evidence_class"] == "avatar_renderer_reported_state"
    assert record["payload"]["renderer_report"]["turn_id"] == "turn-2"
    assert record["payload"]["capture_status"] == "unverified_renderer_self_report"


def test_adopted_body_self_report_preserves_asserted_lineage_without_promoting_it():
    observation = renderer_report_observation(_adopted_body_report())

    assert observation.provenance_class == "godot_adopted_body_renderer_self_report_unverified"
    assert observation.freshness == "unknown"
    assert observation.posture == "synthetic_test"
    assert observation.effect_claimed is False
    assert observation.effect_proven is False
    assert observation.payload["renderer_report"]["body_generation"] == 4
    assert observation.payload["renderer_report"]["renderer_state"]["adopted_body"][
        "pointer_digest"] == "sha256:" + "c" * 64


@pytest.mark.parametrize("field,value", [
    ("pointer_digest", "not-a-digest"),
    ("authority_effects_performed", True),
    ("status", "candidate_unadopted"),
])
def test_adopted_body_self_report_rejects_untrusted_adoption_assertions(field, value):
    report = _adopted_body_report()
    renderer_state = report["renderer_state"]
    assert isinstance(renderer_state, dict)
    adopted_body = renderer_state["adopted_body"]
    assert isinstance(adopted_body, dict)
    adopted_body[field] = value
    _refresh_digest(report)

    with pytest.raises(RendererReportIngressError,
            match="renderer_report_adopted_body_lineage_invalid"):
        renderer_report_observation(report)


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


@pytest.mark.skipif(os.name != "posix", reason="durable renderer store uses POSIX dir-fd custody")
def test_authenticated_renderer_report_returns_to_durable_unverified_world_state(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

        # Exercise the real daemon composition after the authenticated capture
        # owner has closed. The persisted renderer report is available as
        # World-State context, but remains an unverified self-report and never
        # becomes independent effect evidence.
        monkeypatch.setenv("SENTIENTOS_RENDERER_REPORT_EVIDENCE_ROOT",
            str(tmp_path / "renderer-captures"))
        surfaces = RuntimeMaintenanceSurfaces(
            tmp_path, runtime_state_root=tmp_path / "runtime-state")
        surfaces.build_world_state_board(tick_id=now)
        snapshot = surfaces.current_world_state_snapshot
        assert snapshot is not None
        projected = [fact for fact in snapshot.facts
            if fact.subject.subject_kind == "avatar_renderer_reported_state"]
        assert len(projected) == 1
        fact = projected[0]
        assert fact.source.kind == "embodiment"
        assert fact.evidence_strength == "unverified_caller_assertion"
        assert fact.payload["transport_authenticated_at_capture"] is True
        assert fact.payload["renderer_source_independently_authenticated"] is False
        assert fact.payload["renderer_state_independently_observed"] is False
        assert fact.effect_proven is False
        projection_status = surfaces._feedback["surfaces"]["renderer_report_evidence"]
        assert projection_status["status"] == "available"
        assert projection_status["record_count"] == 1
        assert projection_status["renderer_state_independently_observed"] is False

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


@pytest.mark.skipif(os.name != "posix", reason="renderer evidence-store permission checks are POSIX-specific")
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



def _body_pointer_for_report(report: dict[str, object]) -> dict[str, object]:
    from sentientos.avatar_authoring import POINTER_SCHEMA, digest

    renderer_state = report["renderer_state"]
    assert isinstance(renderer_state, dict)
    adopted_body = renderer_state["adopted_body"]
    assert isinstance(adopted_body, dict)
    pointer: dict[str, object] = {
        "schema_version": POINTER_SCHEMA,
        "installation_identity": "installation-test",
        "body_identity": report["body_identity"],
        "body_generation": report["body_generation"],
        "artifact_path": "/private/avatar.glb",
        "artifact_sha256": adopted_body["artifact_sha256"],
        "byte_size": 128,
        "manifest_digest": adopted_body["manifest_digest"],
        "rig_semantic_digest": "sha256:" + "e" * 64,
        "predecessor_generation": 3,
        "adoption_receipt_digest": adopted_body["adoption_receipt_digest"],
        "update_sequence": 4,
    }
    pointer["pointer_digest"] = digest(pointer)
    adopted_body["pointer_digest"] = pointer["pointer_digest"]
    _refresh_digest(report)
    return pointer


def test_adopted_renderer_pointer_comparison_reports_match_without_promoting_authority():
    from sentientos.avatar_renderer_report_ingress import (
        compare_adopted_renderer_report_to_body_pointer,
    )

    report = _adopted_body_report()
    pointer = _body_pointer_for_report(report)

    comparison = compare_adopted_renderer_report_to_body_pointer(report, pointer)

    assert comparison["lineage_match"] is True
    assert comparison["status"] == "lineage_match"
    assert comparison["renderer_self_report_only"] is True
    assert comparison["adoption_authority_verified"] is False
    assert comparison["renderer_effect_proven"] is False
    assert comparison["independent_observation"] is False


def test_adopted_renderer_pointer_comparison_reports_lineage_mismatch():
    from sentientos.avatar_authoring import digest
    from sentientos.avatar_renderer_report_ingress import (
        compare_adopted_renderer_report_to_body_pointer,
    )

    report = _adopted_body_report()
    pointer = _body_pointer_for_report(report)
    pointer["body_generation"] = 5
    pointer["pointer_digest"] = digest({
        key: value for key, value in pointer.items() if key != "pointer_digest"
    })

    comparison = compare_adopted_renderer_report_to_body_pointer(report, pointer)

    assert comparison["lineage_match"] is False
    assert comparison["status"] == "lineage_mismatch"
    assert comparison["adoption_authority_verified"] is False


def test_adopted_renderer_pointer_comparison_rejects_tampered_pointer_digest():
    from sentientos.avatar_renderer_report_ingress import (
        RendererReportIngressError,
        compare_adopted_renderer_report_to_body_pointer,
    )

    report = _adopted_body_report()
    pointer = _body_pointer_for_report(report)
    pointer["artifact_path"] = "/changed/avatar.glb"

    with pytest.raises(RendererReportIngressError,
            match="renderer_body_pointer_integrity_invalid"):
        compare_adopted_renderer_report_to_body_pointer(report, pointer)



def test_local_runner_renderer_receipt_requires_fresh_exact_turn_and_pointer_match():
    from types import SimpleNamespace
    from scripts.run_local_companion_dev import _LatestRendererObservation

    report = _adopted_body_report()
    report.update({
        "consequence_expectation_id": "expectation:test",
        "consequence_expectation_digest": "sha256:" + "1" * 64,
        "consequence_handoff_id": "handoff:test",
        "consequence_handoff_digest": "sha256:" + "2" * 64,
        "consequence_correlation_id": "trial:test",
    })
    _refresh_digest(report)
    pointer = _body_pointer_for_report(report)
    owner = _LatestRendererObservation(
        adopted_body_pointer=pointer, max_age_seconds=5.0)
    owner.update(report)
    expectation = SimpleNamespace(
        expectation_id="expectation:test",
        expectation_digest="sha256:" + "1" * 64,
        correlation_id="trial:test",
        body_generation=4,
    )
    handoff = {
        "handoff_id": "handoff:test",
        "handoff_digest": "sha256:" + "2" * 64,
    }

    receipt = owner.renderer_receipt_for(
        expectation=expectation, handoff=handoff,
        session_id="session-1", turn_id="turn-2", output_digest="a" * 64)

    assert receipt is not None
    assert receipt.report_id == "godot-renderer:godot-demo-12345:1"
    assert receipt.expectation_id == expectation.expectation_id
    assert owner.renderer_receipt_for(
        expectation=expectation, handoff=handoff,
        session_id="session-1", turn_id="wrong-turn", output_digest="a" * 64) is None
    intervening_update = dict(report)
    intervening_update.update(sequence=2, turn_id="turn-3", output_digest="b" * 64)
    _refresh_digest(intervening_update)
    owner.update(intervening_update)
    assert owner.renderer_receipt_for(
        expectation=expectation, handoff=handoff,
        session_id="session-1", turn_id="turn-2", output_digest="a" * 64) is None
    owner._sampled_monotonic = time.monotonic() - 10
    assert owner.renderer_receipt_for(
        expectation=expectation, handoff=handoff,
        session_id="session-1", turn_id="turn-2", output_digest="a" * 64) is None


def test_local_runner_only_exposes_proprioception_when_adopted_pointer_lineage_matches():
    from scripts.run_local_companion_dev import _LatestRendererObservation

    report = _adopted_body_report()
    pointer = _body_pointer_for_report(report)
    owner = _LatestRendererObservation(adopted_body_pointer=pointer)
    owner.update(report)

    observations = owner()

    assert len(observations) == 1
    payload = observations[0].payload
    comparison = payload["body_pointer_comparison"]
    assert comparison["lineage_match"] is True
    assert comparison["adoption_authority_verified"] is False
    assert comparison["renderer_effect_proven"] is False
    assert owner.body_pointer_comparison() == comparison


def test_local_runner_withholds_mismatched_adopted_body_from_proprioception():
    from sentientos.avatar_authoring import digest
    from scripts.run_local_companion_dev import _LatestRendererObservation

    report = _adopted_body_report()
    pointer = _body_pointer_for_report(report)
    pointer["body_generation"] = 5
    pointer["pointer_digest"] = digest({
        key: value for key, value in pointer.items() if key != "pointer_digest"
    })
    owner = _LatestRendererObservation(adopted_body_pointer=pointer)
    owner.update(report)

    assert owner() == ()
    comparison = owner.body_pointer_comparison()
    assert comparison is not None
    assert comparison["lineage_match"] is False
    assert comparison["status"] == "lineage_mismatch"



@pytest.mark.parametrize(("field", "value"), [
    ("installation_identity", "../other-install"),
    ("artifact_path", ""),
    ("byte_size", True),
    ("update_sequence", True),
    ("rig_semantic_digest", "not-a-digest"),
    ("adoption_receipt_digest", "unverified"),
])
def test_adopted_renderer_pointer_comparison_rejects_malformed_pointer_fields(
        field: str, value: object):
    from sentientos.avatar_authoring import digest
    from sentientos.avatar_renderer_report_ingress import (
        compare_adopted_renderer_report_to_body_pointer,
    )

    report = _adopted_body_report()
    pointer = _body_pointer_for_report(report)
    pointer[field] = value
    pointer["pointer_digest"] = digest({
        key: item for key, item in pointer.items() if key != "pointer_digest"
    })

    with pytest.raises(RendererReportIngressError,
            match="renderer_body_pointer_integrity_invalid"):
        compare_adopted_renderer_report_to_body_pointer(report, pointer)


def test_renderer_report_preserves_complete_consequence_command_lineage():
    report = _report()
    lineage = {
        "consequence_expectation_id": "expectation:lineage-1",
        "consequence_expectation_digest": "sha256:" + "1" * 64,
        "consequence_handoff_id": "handoff:lineage-1",
        "consequence_handoff_digest": "sha256:" + "2" * 64,
        "consequence_correlation_id": "correlation:lineage-1",
    }
    report.update(lineage)
    _refresh_digest(report)
    observation = renderer_report_observation(report)
    assert observation is not None

    partial = _report()
    partial["consequence_handoff_id"] = "handoff:lineage-1"
    _refresh_digest(partial)
    with pytest.raises(RendererReportIngressError,
            match="renderer_report_shape_invalid|renderer_report_consequence_lineage_invalid"):
        renderer_report_observation(partial)


def test_adopted_renderer_receipt_preserves_exact_action_lineage_without_effect_proof():
    report = _adopted_body_report()
    report.update({
        "session_id": "session-1",
        "turn_id": "turn-2",
        "output_digest": "e" * 64,
        "output_mode": "chat_response_visual_only",
        "consequence_expectation_id": "expectation:test",
        "consequence_expectation_digest": "sha256:" + "1" * 64,
        "consequence_handoff_id": "handoff:test",
        "consequence_handoff_digest": "sha256:" + "2" * 64,
        "consequence_correlation_id": "trial:test",
    })
    _refresh_digest(report)

    receipt = renderer_report_receipt_identity(report)

    assert receipt.report_id == "godot-renderer:godot-demo-12345:1"
    assert receipt.report_digest == renderer_report_observation(report).source_digest
    assert receipt.session_id == "session-1" and receipt.turn_id == "turn-2"
    assert receipt.output_digest == "e" * 64
    assert receipt.expectation_id == "expectation:test"
    assert receipt.handoff_id == "handoff:test"
    assert receipt.correlation_id == "trial:test"
    assert receipt.body_generation == 4
    verify_renderer_report_receipt_identity(receipt)
    assert renderer_report_observation(report).effect_proven is False

    from dataclasses import replace
    with pytest.raises(RendererReportIngressError, match="receipt_identity_invalid"):
        verify_renderer_report_receipt_identity(replace(receipt, report_id="forged-renderer-id"))
