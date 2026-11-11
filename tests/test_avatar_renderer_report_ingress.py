from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
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


def test_local_dev_renderer_generation_uses_ingress_namespace(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    from scripts.local_companion_edge_dev_worker import _renderer_generation_id
    from scripts.run_local_companion_dev import _LatestRendererObservation

    report = _report()
    report["renderer_generation_id"] = _renderer_generation_id(12345)
    _refresh_digest(report)

    observation = renderer_report_observation(report)
    renderer_report = observation.payload["renderer_report"]
    assert renderer_report["renderer_generation_id"] == "godot-demo-dev-12345"
    provider = _LatestRendererObservation()
    provider.update(report)
    assert provider() == (observation,)
    assert observation.effect_proven is False


@pytest.mark.skipif(os.name != "posix", reason="durable renderer store uses POSIX dir-fd custody")
def test_authenticated_renderer_report_returns_to_durable_unverified_world_state(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from tests.test_resident_developmental_cognition import (
        FakeInvoker, owner as developmental_owner,
    )

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
        cognition, fake = developmental_owner(
            tmp_path / "cognition", allowed_source_kinds=("embodiment",),
            max_selected_facts=1)
        surfaces = RuntimeMaintenanceSurfaces(
            tmp_path, runtime_state_root=tmp_path / "runtime-state",
            resident_developmental_owner=cognition)  # type: ignore[arg-type]
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

        # Verify that the daemon's configured resident cognition owner can
        # actually select this admitted World-State fact. Transport
        # authentication and cognition admission do not upgrade the renderer
        # self-report into independent observation or effect proof.
        cognition_result = surfaces.run_resident_developmental_cognition(tick_id=now)
        assert cognition_result["status"] == "completed"
        assert cognition_result["written_record_id"]
        interpretation = next(request for request in fake.requests
            if request.purpose == "resident_developmental_interpretation")
        selection = json.loads(interpretation.prompt)["selection"]["facts"]
        assert len(selection) == 1
        assert selection[0]["fact_id"] == fact.fact_id
        assert selection[0]["source"]["source_id"] == fact.source.source_id
        assert selection[0]["effect_proven"] is False
        retained = cognition.writeback.store.get(cognition_result["written_record_id"])
        assert retained.candidate["selected_facts"][0]["source"]["source_id"] == (
            fact.source.source_id)
        assert retained.candidate["selected_facts"][0]["effect_proven"] is False
        from sentientos.resident_developmental_cognition import (
            _historical_embodiment_evidence_context,
        )
        compact_history = _historical_embodiment_evidence_context(
            retained.candidate, compact_for_input_budget=True)
        assert compact_history[0]["historical_only"] is True
        assert compact_history[0]["current_truth"] is False
        assert compact_history[0]["authority"] is False
        assert compact_history[0]["effect_proven"] is False
        assert compact_history[0]["reported_values"]["renderer_self_report"][
            "reported_state"]["motion"]["active_motion"] == "wave"
        version_two_candidate = copy.deepcopy(retained.candidate)
        version_two_report = version_two_candidate["selected_facts"][0]["payload"][
            "renderer_report"]
        version_two_report["schema_version"] = "sentientos.avatar_renderer_report:v2"
        version_two_report["renderer_state"]["speech"] = {
            "status": "idle", "mouth_shape": "closed", "mouth_weight": 0.0,
            "timing_event": "speech_finished", "timing_source": "governed_local_tts",
            "phoneme_claimed": False,
        }
        version_two_history = _historical_embodiment_evidence_context(
            version_two_candidate)
        version_two_fields = version_two_history[0]["typed_report_fields"]
        assert version_two_fields["renderer_state"]["speech"]["status"] == "idle"
        assert version_two_fields["renderer_state"]["speech"]["phoneme_claimed"] is False
        assert set(version_two_fields["renderer_state"]["motion"]) == {
            "active_motion", "animation_player_active"}
        assert "transport_provenance" not in version_two_fields

        later_tick = (datetime.fromisoformat(now) + timedelta(seconds=1)).isoformat()
        later_cognition, later_fake = developmental_owner(
            tmp_path / "cognition", allowed_source_kinds=("embodiment",),
            max_selected_facts=1)
        later_surfaces = RuntimeMaintenanceSurfaces(
            tmp_path, runtime_state_root=tmp_path / "runtime-state-later",
            resident_developmental_owner=later_cognition)  # type: ignore[arg-type]
        later_surfaces.build_world_state_board(tick_id=later_tick)
        later_result = later_surfaces.run_resident_developmental_cognition(
            tick_id=later_tick)
        assert later_result["written_record_id"]
        retrieval = next(request for request in later_fake.requests
            if request.purpose == "resident_developmental_retrieval_cognition")
        retrieval_input = json.loads(retrieval.prompt)
        prior_packet = next(packet for packet in retrieval_input["developmental_history"]
            if packet["record_id"] == cognition_result["written_record_id"])
        renderer_history = [item for item in retrieval_input[
            "historical_embodiment_reports"]
            if item["record_id"] == prior_packet["record_id"]]
        assert len(renderer_history) == 1
        historical_report = renderer_history[0]
        assert historical_report["subject_kind"] == "avatar_renderer_reported_state"
        assert historical_report["historical_only"] is True
        assert historical_report["current_truth"] is False
        assert historical_report["authority"] is False
        assert historical_report["effect_proven"] is False
        typed_report = historical_report["typed_report_fields"]
        assert typed_report["renderer_state"]["motion"]["active_motion"] == "wave"
        assert typed_report["renderer_effect_proven"] is False
        assert typed_report["renderer_independent_observation"] is False
        assert typed_report["transport_authenticated_at_capture"] is True
        assert typed_report["renderer_state_independently_observed"] is False

        # Exercise the existing matched intervention owner with this exact
        # retained renderer record. The fake supplies condition-specific
        # outputs, so this verifies wiring and lineage only; it is not evidence
        # that a live model changed its decision or improved performance.
        comparison_fake = FakeInvoker()
        comparison_fake.companion_output_by_condition = {
            "history_present": {
                "disposition": "answer",
                "response": json.dumps({"requested_pose": "wave",
                    "predicted_pose": "wave"}),
                "evidence_ids": ["__CURRENT_FACT__"],
                "history_record_ids": ["__CURRENT_HISTORY__"],
            },
            "history_withheld": {
                "disposition": "answer",
                "response": json.dumps({"requested_pose": "idle",
                    "predicted_pose": "idle"}),
                "evidence_ids": ["__CURRENT_FACT__"],
                "history_record_ids": [],
            },
            "history_restored": {
                "disposition": "answer",
                "response": json.dumps({"requested_pose": "wave",
                    "predicted_pose": "wave"}),
                "evidence_ids": ["__CURRENT_FACT__"],
                "history_record_ids": ["__CURRENT_HISTORY__"],
            },
        }
        comparison_owner, _ = developmental_owner(
            tmp_path / "cognition", comparison=True, invoker=comparison_fake,
            allowed_source_kinds=("embodiment",), max_selected_facts=1)
        assert later_surfaces.current_world_state_snapshot is not None
        comparison = comparison_owner.run_companion_history_intervention(
            snapshot=later_surfaces.current_world_state_snapshot,
            tick_id="renderer-history-causal-comparison",
            question=("Use the retained renderer report to choose a requested pose "
                "and predict its renderer-reported pose. Return JSON with "
                "requested_pose and predicted_pose."),
            history_record_allowlist=(cognition_result["written_record_id"],))
        assert comparison.status == "completed_controlled_intervention"
        assert comparison.response_text_classification == (
            "history_presence_associated_stable_response_text_difference")
        assert comparison.restored_prompt_matches is True
        assert comparison.conditions[0]["retrieved_record_ids"] == [
            cognition_result["written_record_id"]]
        assert comparison.conditions[1]["retrieved_record_ids"] == []
        assert comparison.conditions[0]["retrieved_record_ids"] == (
            comparison.conditions[2]["retrieved_record_ids"])
        controls = [condition["matched_control_inputs"]
            for condition in comparison.conditions]
        assert controls[0] == controls[1] == controls[2]
        condition_requests = {request.linkage["condition_id"]: request
            for request in comparison_fake.requests
            if request.linkage.get("condition_id") in {
                "history_present", "history_withheld", "history_restored"}}
        assert set(condition_requests) == {
            "history_present", "history_withheld", "history_restored"}
        for condition_id in ("history_present", "history_restored"):
            prompt = json.loads(condition_requests[condition_id].prompt)
            assert any(packet["record_id"] == cognition_result["written_record_id"]
                for packet in prompt["developmental_history"])
            evidence = next(item for item in prompt["historical_embodiment_reports"]
                if item["record_id"] == cognition_result["written_record_id"])
            reported_state = (evidence.get("typed_report_fields", {}).get(
                "renderer_state") or evidence["reported_values"][
                "renderer_self_report"]["reported_state"])
            assert reported_state["motion"]["active_motion"] == "wave"
            assert evidence["effect_proven"] is False
        withheld_prompt = json.loads(condition_requests["history_withheld"].prompt)
        assert withheld_prompt["developmental_history"] == []
        assert withheld_prompt.get("historical_embodiment_reports", []) == []

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

def test_history_projection_accepts_direct_renderer_report_fact_payload():
    from sentientos.resident_developmental_cognition import (
        CurrentWorldStateCognitiveProjection,
        _current_evidence_prompt_payload,
        _historical_embodiment_evidence_context,
    )

    report = _report()
    fact_id = "fact-renderer-report"
    fact = {
        "fact_id": fact_id,
        "source": {"kind": "embodiment",
            "source_id": "renderer-report:direct-payload",
            "schema_version": report["schema_version"]},
        "subject": {"subject_kind": "avatar_renderer_report"},
        "stage": "observation", "disposition": "recorded",
        "evidence_strength": "renderer_self_report",
        "effect_proven": False, "observed_at": report["reported_at"],
        "payload": report,
    }
    candidate = {"selected_fact_ids": [fact_id], "selected_facts": [fact]}

    projected = _historical_embodiment_evidence_context(candidate)

    assert len(projected) == 1
    assert projected[0]["semantic_report_roles"]["renderer_self_report"][
        "reported_state"]["motion"]["active_motion"] == "wave"
    assert projected[0]["effect_proven"] is False
    assert projected[0]["authority"] is False

    source = {"kind": "embodiment",
        "source_id": "renderer-report:direct-payload",
        "schema_version": report["schema_version"],
        "digest": "sha256:" + "a" * 64}
    run_id = "developmental-history-run:sample"
    run_source = {"kind": "embodiment", "source_id": run_id,
        "schema_version": "sentientos.developmental_history_intervention_run:v2",
        "digest": "sha256:" + "d" * 64}
    run_fact = {"fact_id": "fact-history-run", "source": run_source,
        "subject": {"subject_kind": "developmental_history_intervention_experiment"},
        "stage": "observation", "disposition": "no_observable_history_difference",
        "evidence_strength": "digest_bound_history_intervention_artifact",
        "effect_proven": False, "observed_at": "2026-11-11T00:00:00Z",
        "payload": {"run_id": run_id, "run_digest": "sha256:" + "e" * 64,
            "history_intervention_summary": {"classification": "no_observable_history_difference",
                "present_vs_withheld_difference_observed": False,
                "restored_vs_withheld_difference_observed": False,
                "restored_matches_present": True, "present_restoration_stable": True,
                "claims_posture": "bounded_observed_association_only", "measurements": []},
            "conditions": [{"condition_id": "history_present", "output_digest": "a" * 64,
                "inference_receipt_id": "receipt-present", "inference_receipt_digest": "b" * 64,
                "retrieved_record_ids": ["devrec-example"], "retrieved_record_digests": ["c" * 64]}],
            "objective_evaluation": {"assessment": "preregistered_probe_suite_scored",
                "condition_correct_counts": [3, 3, 3], "history_correct_probe_delta": 0,
                "restoration_correct_probe_delta": 0, "restoration_correctness_stable": True,
                "probe_count": 3, "scope": "bounded_synthetic_task",
                "model_behavior_posture": "receipt_bound"},
            "objective_task_family": "sample-family",
            "objective_task_commitment_posture": "salted_private_oracle_commitment:v1",
            "acquisition_examples": [], "execution_evidence_posture": "receipts_checked",
            "independent_backend_observation": False, "learning_established": False}}
    run_fact["payload"]["source_audit_detail"] = "x" * 12_000
    detailed_run_summary = _historical_embodiment_evidence_context({
        "selected_fact_ids": [run_fact["fact_id"]], "selected_facts": [run_fact]})
    assert detailed_run_summary[0]["semantic_report_roles"][
        "history_intervention_result"]["classification"] == (
            "no_observable_history_difference")
    assert detailed_run_summary[0]["typed_report_fields"] == {}
    extra_facts = []
    extra_sources = []
    for index, (schema, fields, payload) in enumerate((
            ("sentientos.embodied_action_expectation:v1",
                ("expectation_id", "handoff_id", "requested", "predicted_observables",
                    "observable_fields", "expected_observation_source_class"),
                {"expectation_id": "expectation-a", "handoff_id": "handoff-a",
                    "requested": {"pose": "nod"}, "predicted_observables": {"pose": "nod"},
                    "observable_fields": ["pose"],
                    "expected_observation_source_class": "independent_observer"}),
            ("sentientos.avatar_renderer_handoff:v1",
                ("handoff_id", "requested_test_pose", "requested_test_expression",
                    "renderer_reported", "independently_observed"),
                {"handoff_id": "handoff-a", "requested_test_pose": "nod",
                    "requested_test_expression": "neutral", "renderer_reported": True,
                    "independently_observed": False}),
            ("sentientos.embodied_consequence_chain:v1",
                ("chain_id", "component_source_ids", "component_record_digests",
                    "event_times", "independent_observation_posture", "effect_proven"),
                {"chain_id": "chain-a", "component_source_ids": ["expectation-a", "handoff-a"],
                    "component_record_digests": ["sha256:" + "1" * 64],
                    "event_times": {"expected": "t1"},
                    "independent_observation_posture": "insufficient", "effect_proven": False}),
            )):
        source_item = {"kind": "embodiment", "source_id": f"embodiment:{index}",
            "schema_version": schema, "digest": "sha256:" + str(index) * 64}
        fact_item = {"fact_id": f"fact-embodiment-{index}", "source": source_item,
            "subject": {"subject_kind": schema.rsplit(":", 1)[0]},
            "stage": "observation", "disposition": "recorded",
            "evidence_strength": "typed_source_evidence", "effect_proven": False,
            "observed_at": "2026-11-11T00:00:01Z",
            "payload": {"schema_version": schema, **payload}}
        extra_facts.append(fact_item)
        extra_sources.append(source_item)
    current_facts = (fact, run_fact, *extra_facts)
    current_sources = (source, run_source, *extra_sources)
    current = CurrentWorldStateCognitiveProjection(
        snapshot_id="snapshot-current", snapshot_digest="sha256:" + "b" * 64,
        facts=current_facts, sources=current_sources, conflicts=(),
        fact_ids=tuple(item["fact_id"] for item in current_facts),
        projection_id="current-projection", projection_digest="sha256:" + "c" * 64)
    compact = _current_evidence_prompt_payload(current)
    assert compact["fact_ids"] == [item["fact_id"] for item in current_facts]
    assert compact["projection_digest"] == current.projection_digest
    assert compact["fact_row_schema"] == "sentientos.current_world_state_fact_row:v1"
    assert all(len(row) == len(compact["fact_row_fields"]) for row in compact["facts"])
    rows = [dict(zip(compact["fact_row_fields"], row)) for row in compact["facts"]]
    assert rows[0]["source_id"] == source["source_id"]
    assert compact["evidence_posture"]["current_observation"] is True
    assert compact["evidence_posture"]["historical_only"] is False
    assert compact["sources_digest"]
    assert rows[0]["reported_values"]["renderer_self_report"][
        "reported_state"]["motion"]["active_motion"] == "wave"
    expectation = next(item for item in rows if item["source_schema_version"]
        == "sentientos.embodied_action_expectation:v1")
    assert expectation["reported_values"]["action_expectation"]["requested"] == {"pose": "nod"}
    handoff = next(item for item in rows if item["source_schema_version"]
        == "sentientos.avatar_renderer_handoff:v1")
    assert handoff["reported_values"]["renderer_handoff"]["independently_observed"] is False
    chain = next(item for item in rows if item["source_schema_version"]
        == "sentientos.embodied_consequence_chain:v1")
    assert chain["reported_values"]["consequence_chain"]["effect_proven"] is False
    run_summary = rows[1]["reported_values"]["history_intervention_result"]
    assert run_summary["classification"] == "no_observable_history_difference"
    assert run_summary["objective_evaluation"]["condition_correct_counts"] == [3, 3, 3]
    assert run_summary["conditions"][0]["retrieved_record_ids"] == ["devrec-example"]
    assert len(json.dumps(compact, sort_keys=True, separators=(",", ":"))) < len(
        json.dumps(current.semantic_payload(), sort_keys=True, separators=(",", ":")))
