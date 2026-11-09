from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from scripts.avatar_authoring import renderer_handoff
from sentientos.avatar_renderer_report_ingress import (
    renderer_report_observation, renderer_report_receipt_identity,
)
from sentientos.avatar_consequence_bridge import (
    AvatarConsequenceCaptureRequestHandler,
    AvatarConsequenceMeasurementRequestSender,
    RemoteAvatarConsequenceObserver,
)
from sentientos.embodied_consequence import (
    AuthenticatedBridgeIndependentObserver,
    ConsequenceStore,
    SyntheticRenderer,
    evaluate_consequence,
    make_expectation,
    world_state_records,
)
from sentientos.gaming_companion_bridge import (
    AVATAR_CONSEQUENCE_REQUEST_SCHEMA, CompanionBridgeReceiver, encode_message,
)
from sentientos.gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
)

pytestmark = pytest.mark.no_legacy_skip


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _adopted_renderer_report_for(expectation, handoff):
    report = {
        "schema_version": "sentientos.avatar_renderer_report:v2",
        "evidence_class": "avatar_renderer_reported_state",
        "source_id": "godot-adopted-body-demo",
        "renderer_generation_id": "godot-demo-12345",
        "sequence": 1,
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "session_id": "avatar-trial-session",
        "turn_id": "assistant-turn-1",
        "output_digest": _sha("authorized assistant text"),
        "output_mode": "chat_response_visual_only",
        "commanded_state": {
            "expression": "neutral", "mood": "calm", "intensity": 0.0,
            "motion": "wave", "workload_mode": "gaming",
        },
        "renderer_state": {
            "expression": {"status": "procedural_fallback_applied"},
            "motion": {
                "active_motion": "wave", "animation_player_active": False,
                "head_rotation_radians": {"x": 0.0, "y": 0.0, "z": 0.0},
                "left_arm_rotation_radians": {"x": 0.0, "y": 0.0, "z": -0.39},
                "body_position": {"x": 0.0, "y": 0.66, "z": 0.0},
                "observed_nodes": {"head": True, "left_arm": True, "body": True},
            },
            "applied_render_cap_fps": 15,
            "speech": {"status": "not_requested", "phoneme_claimed": False},
            "adopted_body": {
                "status": "active",
                "evidence_posture": "trusted_loader_adoption_receipt_verified",
                "artifact_sha256": "a" * 64,
                "manifest_digest": "sha256:" + "b" * 64,
                "pointer_digest": "sha256:" + "c" * 64,
                "adoption_receipt_digest": "sha256:" + "d" * 64,
                "authority_effects_performed": False,
            },
        },
        "frame_delta_seconds": 0.016,
        "apply_duration_usec": 500,
        "body_identity": "companion-avatar-v4",
        "body_generation": expectation.body_generation,
        "effect_proven": False,
        "independent_observation": False,
        "consequence_expectation_id": expectation.expectation_id,
        "consequence_expectation_digest": expectation.expectation_digest,
        "consequence_handoff_id": handoff["handoff_id"],
        "consequence_handoff_digest": handoff["handoff_digest"],
        "consequence_correlation_id": expectation.correlation_id,
        "source_digest": "",
    }
    report["source_digest"] = "sha256:" + hashlib.sha256(json.dumps(
        {key: value for key, value in report.items() if key != "source_digest"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return report


def test_explicit_avatar_measurement_traverses_authenticated_consequence_stream(tmp_path):
    now = datetime.now(timezone.utc)
    command_at = (now - timedelta(seconds=3)).isoformat()
    report_done = (now - timedelta(seconds=2)).isoformat()
    observed_at = (now - timedelta(milliseconds=500)).isoformat()
    body = {
        "installation_identity": "installation-test",
        "body_identity": "avatar-test",
        "body_generation": 1,
        "artifact_sha256": "sha256:" + "a" * 64,
        "manifest_digest": "sha256:" + "b" * 64,
        "pointer_digest": "sha256:" + "c" * 64,
    }
    handoff = renderer_handoff(
        body, renderer_interface_id="renderer:test:v1", requested_pose="wave",
        requested_expression="neutral", correlation_id="avatar-trial-1",
        commanded_at=command_at)
    expectation = make_expectation(
        installation_body_id="installation-test", body_id="avatar-test",
        body_generation=1, body_manifest_digest=body["manifest_digest"],
        handoff_id=handoff["handoff_id"], handoff_digest=handoff["handoff_digest"],
        renderer_interface_id="renderer:test:v1",
        requested={"pose": "wave"},
        predicted_observables={"avatar_visible": True, "avatar_motion": "wave"},
        observable_fields=("avatar_visible", "avatar_motion"),
        comparison_policy={"avatar_visible": {"kind": "exact"},
                           "avatar_motion": {"kind": "exact"}},
        expected_observation_source_class="authenticated_bridge_observer",
        correlation_id="avatar-trial-1", causal_principal_binding_digest=None,
        created_at=command_at, expires_at=(now + timedelta(minutes=2)).isoformat())
    report = SyntheticRenderer(applied={"pose": "wave", "expression": "neutral"},
        started_at=command_at, completed_at=report_done).render_test(handoff)

    request_key = b"r" * 32
    consequence_key = b"c" * 32
    ack_key = b"a" * 32
    request_receiver = CompanionBridgeReceiver(
        source_keys={"wsl-avatar-request": request_key},
        expected_generations={"wsl-avatar-request": "request-gen-1"})
    consequence_runtime = CompanionBridgeLoopbackRuntime(
        receiver=CompanionBridgeReceiver(
            source_keys={"windows-avatar-observer": consequence_key},
            expected_generations={"windows-avatar-observer": "observer-gen-1"}),
        acknowledgment_source_id="wsl-avatar-ack",
        acknowledgment_generation_id="ack-gen-1", acknowledgment_key=ack_key,
        socket_timeout_seconds=1.0)
    consequence_port = consequence_runtime.start()
    consequence_client = CompanionBridgeLoopbackClient(
        port=consequence_port,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-avatar-ack": ack_key},
            expected_generations={"wsl-avatar-ack": "ack-gen-1"}),
        timeout_seconds=1.0)
    capture_digest = _sha("captured-pixels")
    process_digest = _sha("Cronos-Win64-Shipping.exe")
    consent_digest = _sha("operator-consent-id")
    sample_digests = [_sha("avatar-frame-1"), _sha("avatar-frame-2"), capture_digest]
    sample_times = [
        (now - timedelta(seconds=1.5)).isoformat(),
        (now - timedelta(seconds=1)).isoformat(),
        observed_at,
    ]
    sample_offsets = [0.0, 0.5, 1.0]
    sequence_binding = {
        "sample_capture_digests": sample_digests,
        "sample_captured_at": sample_times,
        "sample_offsets_seconds": sample_offsets,
        "process_name_digest": process_digest,
        "consent_id_digest": consent_digest,
        "capture_scope": "allowlisted_foreground_game_client_area",
    }
    sequence_digest = hashlib.sha256(json.dumps(
        sequence_binding, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("utf-8")).hexdigest()
    measurement = {
        "observed": {"avatar_visible": True, "avatar_motion": "wave"},
        "observed_at": observed_at,
        "capture_digest": capture_digest,
        "capture_sequence_digest": sequence_digest,
        "sample_capture_digests": sample_digests,
        "sample_captured_at": sample_times,
        "sample_offsets_seconds": sample_offsets,
        "process_name_digest": process_digest,
        "consent_id_digest": consent_digest,
        "capture_scope": "allowlisted_foreground_game_client_area",
        "confidence": "unknown",
        "quality": "partial",
        "raw_frame_retained": False,
    }
    handler = AvatarConsequenceCaptureRequestHandler(
        observe=lambda: measurement, client=consequence_client,
        request_source_id="wsl-avatar-request", request_generation_id="request-gen-1",
        observer_id="windows-avatar-observer", observer_generation_id="observer-gen-1",
        session_id="avatar-trial-session", observer_source_key=consequence_key)

    class _RequestClient:
        def send(self, encoded):
            request = request_receiver.accept(encoded)
            assert handler(request) is True
            return request

    sender = AvatarConsequenceMeasurementRequestSender(
        client=_RequestClient(), source_id="wsl-avatar-request",
        session_id="avatar-trial-session", generation_id="request-gen-1",
        source_key=request_key)
    observer_owner = AuthenticatedBridgeIndependentObserver(
        runtime=consequence_runtime, observer_id="windows-avatar-observer",
        generation_id="observer-gen-1", receive_timeout_seconds=1.0)
    remote = RemoteAvatarConsequenceObserver(
        request_sender=sender, observer=observer_owner)
    try:
        observation = remote.observe(
            expectation=expectation, handoff=handoff, report=report)
        attribution, comparison = evaluate_consequence(
            expectation=expectation, handoff=handoff, current_body=body,
            renderer_report=report, observation=observation,
            independent_observer_owner=remote,
            evaluated_at=datetime.now(timezone.utc).isoformat())
        receipt = attribution["observation_authentication_receipt"]
        assert receipt["capture_provenance"] == {
            "schema_version": "sentientos.screen_capture_provenance:v2",
            "capture_digest": capture_digest,
            "process_name_digest": process_digest,
            "consent_id_digest": consent_digest,
            "capture_scope": "allowlisted_foreground_game_client_area",
            "raw_frame_retained": False,
            "capture_sequence_digest": sequence_digest,
            "sample_capture_digests": sample_digests,
            "sample_captured_at": sample_times,
            "sample_offsets_seconds": sample_offsets,
        }
        assert receipt["capture_request_id"]
        assert comparison["counts"]["satisfied"] == 2
        assert attribution["classification"] == "indeterminate"
        assert attribution["effect_proven"] is False
        assert attribution["causal_attribution_posture"] != "causally_established"


        # Carry a Godot self-report as an untrusted reference through authenticated capture.
        renderer_report = _adopted_renderer_report_for(expectation, handoff)
        renderer_receipt = renderer_report_receipt_identity(renderer_report)
        receipt_observation = remote.observe(
            expectation=expectation, handoff=handoff, renderer_receipt=renderer_receipt)
        receipt_attribution, receipt_comparison = evaluate_consequence(
            expectation=expectation, handoff=handoff, current_body=body,
            renderer_report=None, observation=receipt_observation,
            independent_observer_owner=remote,
            evaluated_at=datetime.now(timezone.utc).isoformat())
        records = world_state_records(
            expectation=expectation, handoff=handoff, renderer_report=None,
            observation=receipt_observation, attribution=receipt_attribution,
            comparison=receipt_comparison)
        assert renderer_report_observation(renderer_report).effect_proven is False
        assert receipt_observation.renderer_report_id == renderer_receipt.report_id
        assert receipt_observation.renderer_report_digest == renderer_receipt.report_digest
        assert receipt_attribution["renderer_report_id"] == renderer_receipt.report_id
        assert receipt_attribution["renderer_report_digest"] == renderer_receipt.report_digest
        assert receipt_attribution["effect_proven"] is False
        assert receipt_attribution["classification"] == "indeterminate"
        assert all(record["effect_proven"] is False for record in records)
        attribution_record = next(record for record in records
            if record["source_id"] == receipt_attribution["attribution_id"])
        assert attribution_record["payload"]["renderer_report_id"] == renderer_receipt.report_id
        assert attribution_record["payload"]["renderer_report_digest"] == renderer_receipt.report_digest
        store = ConsequenceStore(tmp_path / "renderer-receipt-chain")
        chain = store.put_consequence_chain(
            expectation=expectation, handoff=handoff, renderer_report=None,
            observation=receipt_observation, attribution=receipt_attribution,
            comparison=receipt_comparison)
        loaded = store.load_verified_consequence_chain(chain["chain_id"])
        assert loaded["renderer_report"] is None
        assert loaded["observation"]["renderer_report_id"] == renderer_receipt.report_id
        assert loaded["observation"]["renderer_report_digest"] == renderer_receipt.report_digest
        reloaded_records = store.world_state_records(
            consequence_chain_ids=(chain["chain_id"],))
        reloaded_attribution = next(record for record in reloaded_records
            if record["source_id"] == receipt_attribution["attribution_id"])
        assert reloaded_attribution["payload"]["renderer_report_id"] == renderer_receipt.report_id
        assert reloaded_attribution["payload"]["renderer_report_digest"] == renderer_receipt.report_digest
        assert all(record["effect_proven"] is False for record in reloaded_records)
    finally:
        consequence_runtime.close()


def test_avatar_consequence_handler_rejects_unqualified_capture_output():
    from sentientos.avatar_consequence_bridge import AvatarConsequenceBridgeError

    request_key = b"r" * 32
    request_receiver = CompanionBridgeReceiver(
        source_keys={"request": request_key},
        expected_generations={"request": "r1"})
    payload = {
        "schema_version": AVATAR_CONSEQUENCE_REQUEST_SCHEMA,
        "capture_request_id": "1" * 32,
        "expectation_id": "expectation:test",
        "expectation_digest": "sha256:" + "a" * 64,
        "handoff_id": "handoff:test",
        "handoff_digest": "sha256:" + "b" * 64,
        "renderer_report_id": None, "renderer_report_digest": None,
        "correlation_id": "trial:test", "body_generation": 1,
    }
    request = request_receiver.accept(encode_message(kind="avatar_consequence_request",
        source_id="request", session_id="s", generation_id="r1", sequence=1,
        payload=payload, key=request_key))

    class _NoDelivery:
        def send(self, _encoded):
            raise AssertionError("invalid capture output must not be published")

    handler = AvatarConsequenceCaptureRequestHandler(
        observe=lambda: {"rgb": b"private-frame", "confidence": "high",
                        "quality": "usable", "raw_frame_retained": True},
        client=_NoDelivery(), request_source_id="request", request_generation_id="r1",
        observer_id="observer", observer_generation_id="o1", session_id="s",
        observer_source_key=b"k" * 32)
    with pytest.raises(AvatarConsequenceBridgeError,
                       match="avatar_consequence_measurement_contract_invalid"):
        handler(request)
