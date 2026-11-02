from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Thread

import pytest

from sentientos.gaming_companion_bridge import CompanionBridgeReceiver, VerifiedBridgeMessage
from sentientos.gaming_companion_bridge_runtime import CompanionBridgeLoopbackClient
from sentientos.game_performance_bridge import (
    GamePerformanceBridgeDetector,
    VerifiedGamePerformanceObservation,
    WindowsGamePerformanceBridgePublisher,
)
from sentientos.runtime_governor import RuntimeGovernor
from sentientos.windows_game_performance import WindowsGamePerformanceObserver

pytestmark = pytest.mark.no_legacy_skip


class _Receiver:
    def __init__(self, message: VerifiedBridgeMessage):
        self.message = message

    def receive(self, timeout=None):
        del timeout
        return self.message


def test_windows_performance_sample_is_signed_transported_and_shape_checked():
    source_key = b"windows-performance-source-key-32-bytes"
    source_id, generation = "windows-edge", "edge-generation-1"
    verifier = CompanionBridgeReceiver(source_keys={source_id: source_key},
        expected_generations={source_id: generation})
    observer = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        process_provider=lambda _pid: {"cpu_percent": 12.5, "rss_bytes": 1024},
        frame_provider=lambda _pid: ((16.7, 51.0), "a" * 64))
    client = CompanionBridgeLoopbackClient(port=1,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"core": b"core-acknowledgment-key-32-bytes"},
            expected_generations={"core": "core-generation-1"}))
    captured: list[VerifiedBridgeMessage] = []

    def accept_sample(encoded: bytes) -> VerifiedBridgeMessage:
        message = verifier.accept(encoded)
        captured.append(message)
        return message

    client.send = accept_sample  # type: ignore[method-assign]
    publisher = WindowsGamePerformanceBridgePublisher(observer=observer, client=client,
        source_id=source_id, session_id="session-1", generation_id=generation,
        source_key=source_key, process_id=123)
    publisher.publish_once()

    assert len(captured) == 1
    sample = GamePerformanceBridgeDetector(receiver=_Receiver(captured[0]),
        source_id=source_id, generation_provider=lambda: generation).receive_once()
    assert sample.source_id == source_id
    assert sample.generation_id == generation
    assert sample.sequence == 1
    assert sample.frame_time_p95_ms == 51.0
    assert sample.hitch_count_over_50ms == 1
    assert sample.process_cpu_percent == 12.5
    assert sample.process_rss_bytes == 1024
    assert len(sample.payload_digest) == 64
    assert len(sample.message_id) == 64
    workers = [Thread(target=publisher.publish_once) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=2)
        assert not worker.is_alive()
    assert sorted(message.sequence for message in captured) == [1, 2, 3, 4, 5]


def test_game_performance_detector_rejects_wrong_generation_and_stale_sample():
    source_key = b"windows-performance-source-key-32-bytes"
    now = datetime.now(timezone.utc)
    observer = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        process_provider=lambda _pid: {"cpu_percent": 5.0, "rss_bytes": 2048},
        frame_provider=lambda _pid: ((20.0,), "b" * 64),
        clock=lambda: now.isoformat())
    source_id, generation = "windows-edge", "edge-generation-1"
    verifier = CompanionBridgeReceiver(source_keys={source_id: source_key},
        expected_generations={source_id: generation},
        clock=lambda: now.timestamp())
    from sentientos.gaming_companion_bridge import encode_message

    payload = observer.observe(456).to_dict()
    message = verifier.accept(encode_message(kind="observation", source_id=source_id,
        session_id="session-1", generation_id=generation, sequence=1, payload=payload,
        key=source_key, created_at=payload["observed_at"]))
    with pytest.raises(ValueError, match="game_performance_transport_identity_invalid"):
        GamePerformanceBridgeDetector(receiver=_Receiver(message), source_id=source_id,
            generation_provider=lambda: "rotated-generation").receive_once()

    stale_time = (now - timedelta(seconds=20)).isoformat()
    stale_payload = {**payload, "observed_at": stale_time}
    stale_verifier = CompanionBridgeReceiver(source_keys={source_id: source_key},
        expected_generations={source_id: generation}, clock=lambda: now.timestamp(),
        max_clock_skew_seconds=30.0)
    stale_message = stale_verifier.accept(encode_message(kind="observation", source_id=source_id,
        session_id="session-2", generation_id=generation, sequence=1,
        payload=stale_payload, key=source_key, created_at=stale_time))
    with pytest.raises(ValueError, match="game_performance_observation_stale"):
        GamePerformanceBridgeDetector(receiver=_Receiver(stale_message), source_id=source_id,
            generation_provider=lambda: generation).receive_once()


def test_measured_game_hitches_defer_background_inference_but_not_foreground_chat(
        tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    governor._host_resource_evidence = {
        "evaluation_id": "evaluation-1", "epoch_id": "epoch-1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": "snapshot-1", "report_id": "report-1",
        "report_digest": "c" * 64, "pressure_labels": (),
        "cpu_utilization_percent": 15.0, "ram_utilization_percent": 30.0,
    }
    observation = VerifiedGamePerformanceObservation(
        "windows-edge", "edge-generation-1", 4, "d" * 64, "e" * 64,
        datetime.now(timezone.utc).isoformat(), "f" * 64, 52.0, 1, 20.0,
        4096, "available")
    assert governor.observe_verified_game_performance(observation)
    background = governor.admit_action("local_model_inference", "sentientosd",
        "background-1", {"purpose": "maintenance_summary"})
    assert background.reason == "deferred_background_inference_for_game_frame_pressure"
    assert background.evidence_refs["game_performance_evidence"]["message_id"] == "d" * 64
    foreground = governor.admit_action("local_model_inference", "sentientosd",
        "foreground-1", {"purpose": "local_user_chat"})
    assert foreground.reason == "allowed"
    recovered_observation = VerifiedGamePerformanceObservation(
        "windows-edge", "edge-generation-1", 5, "1" * 64, "2" * 64,
        datetime.now(timezone.utc).isoformat(), "f" * 64, 16.7, 0, 20.0,
        4096, "available")
    assert governor.observe_verified_game_performance(recovered_observation)
    recovered = governor.admit_action("local_model_inference", "sentientosd",
        "background-1", {"purpose": "maintenance_summary"})
    assert recovered.reason == "allowed"
    assert recovered.evidence_refs["game_frame_pressure"] is False

    governor._host_resource_evidence = None
    missing_core = governor.admit_action("local_model_inference", "sentientosd",
        "background-2", {"purpose": "maintenance_summary"})
    assert missing_core.reason == "deferred_resource_telemetry_incomplete"
