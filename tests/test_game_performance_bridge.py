from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from sentientos.gaming_companion_bridge import CompanionBridgeReceiver, VerifiedBridgeMessage
from sentientos.gaming_companion_bridge_runtime import CompanionBridgeLoopbackClient
from sentientos.game_performance_bridge import (
    GamePerformanceAdmissionRuntime,
    GamePerformanceBridgeDetector,
    VerifiedGamePerformanceObservation,
    WindowsGamePerformanceBridgePublisher,
    WindowsGamePerformanceObservationPump,
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


def test_windows_performance_sample_is_signed_transported_and_shape_checked(
        tmp_path, monkeypatch):
    source_key = b"windows-performance-source-key-32-bytes"
    source_id, generation = "windows-edge", "edge-generation-1"
    verifier = CompanionBridgeReceiver(source_keys={source_id: source_key},
        expected_generations={source_id: generation})
    frame_samples = [((16.7, 51.0), "a" * 64)]
    observed_process_ids = []
    observer = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        process_provider=lambda pid: (observed_process_ids.append(pid)
            or {"name": "cronos.exe", "cpu_percent": 0.0, "rss_bytes": 1024}),
        frame_provider=lambda _pid: frame_samples[0])
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
    assert sample.process_name_digest == hashlib.sha256(b"cronos.exe").hexdigest()
    assert sample.hitch_count_over_50ms == 1
    assert sample.process_cpu_percent == 0.0
    assert sample.process_rss_bytes == 1024
    assert len(sample.payload_digest) == 64
    assert len(sample.message_id) == 64
    frame_samples[0] = ((), "b" * 64)
    publisher.publish_once(process_id=124)
    assert observed_process_ids[:2] == [123, 124]
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    from sentientos.control_plane_kernel import ControlPlaneKernel
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    admission_runtime = GamePerformanceAdmissionRuntime(
        detector=GamePerformanceBridgeDetector(receiver=_Receiver(captured[1]),
            source_id=source_id, generation_provider=lambda: generation),
        admission_owner=kernel)
    assert admission_runtime.receive_once()
    assert admission_runtime.status()["accepted_observations"] == 1
    governor._host_resource_evidence = {
        "evaluation_id": "host-evaluation", "epoch_id": "host-epoch",
        "observation_correlation_id": "bridge-to-governor",
        "snapshot_id": "host-snapshot", "report_id": "host-report",
        "report_digest": "c" * 64,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "pressure_labels": ("cpu_pressure",),
        "cpu_utilization_percent": 96.0, "ram_utilization_percent": 42.0,
        "gpu_telemetry_available": True,
    }
    decision = governor.admit_action("local_model_inference", "sentientosd",
        "bridge-to-governor", {"purpose": "local_user_chat"})
    assert decision.reason == (
        "deferred_local_model_inference_under_host_pressure_during_game")
    assert decision.evidence_refs["game_performance_evidence"][
        "message_id"] == captured[1].message_id
    assert decision.evidence_refs["game_performance_evidence"][
        "frame_time_p95_ms"] is None
    assert decision.evidence_refs["game_performance_evidence"][
        "process_cpu_percent"] == 0.0
    workers = [Thread(target=publisher.publish_once) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=2)
        assert not worker.is_alive()
    assert sorted(message.sequence for message in captured) == [1, 2, 3, 4, 5, 6]


def test_game_performance_pump_only_publishes_selected_allowlisted_process():
    published = Event()
    selected_names = []

    class Publisher:
        def publish_once(self, *, process_id):
            assert process_id == 733
            published.set()
            return SimpleNamespace(created_at=datetime.now(timezone.utc).isoformat())

    pump = WindowsGamePerformanceObservationPump(
        publisher=Publisher(), process_names=("Cronos.exe",),
        interval_seconds=0.1,
        process_selector=lambda names: (selected_names.extend(names) or 733))
    pump.start()
    try:
        assert published.wait(2.0)
    finally:
        pump.close()
    status = pump.status()
    assert selected_names == ["cronos.exe"]
    assert status["published"] == 1
    assert status["running"] is False


def test_game_performance_detector_rejects_wrong_generation_and_stale_sample():
    source_key = b"windows-performance-source-key-32-bytes"
    now = datetime.now(timezone.utc)
    observer = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        process_provider=lambda _pid: {"name": "cronos.exe", "cpu_percent": 5.0,
            "rss_bytes": 2048},
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


def test_detector_normalizes_windows_clock_for_governor_currentness():
    from sentientos.gaming_companion_bridge import encode_message

    source_key = b"windows-performance-source-key-32-bytes"
    source_id, generation = "windows-edge", "edge-generation-1"
    core_now = datetime.now(timezone.utc)
    source_time = core_now + timedelta(seconds=8)
    observer = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        process_provider=lambda _pid: {"name": "cronos.exe", "cpu_percent": 7.0,
            "rss_bytes": 4096},
        frame_provider=lambda _pid: ((), "unused"),
        clock=lambda: source_time.isoformat())
    payload = observer.observe(456).to_dict()
    receiver = CompanionBridgeReceiver(source_keys={source_id: source_key},
        expected_generations={source_id: generation},
        clock=lambda: core_now.timestamp())
    message = receiver.accept(encode_message(kind="observation", source_id=source_id,
        session_id="session-1", generation_id=generation, sequence=1,
        payload=payload, key=source_key, created_at=source_time.isoformat()))

    observation = GamePerformanceBridgeDetector(receiver=_Receiver(message),
        source_id=source_id, generation_provider=lambda: generation,
        clock=lambda: core_now,
        source_clock_offset_seconds=8.0).receive_once()

    assert observation.observed_at == core_now.isoformat()
    assert observation.source_observed_at == source_time.isoformat()
    assert observation.status == "available"
    assert observation.frame_time_p95_ms is None


def test_measured_game_hitches_defer_all_optional_local_inference(
        tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    governor._host_resource_evidence = {
        "evaluation_id": "evaluation-1", "epoch_id": "epoch-1",
        "observation_correlation_id": "game-frame-test",
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
    assert background.reason == "deferred_local_model_inference_for_game_frame_pressure"
    assert background.evidence_refs["game_performance_evidence"]["message_id"] == "d" * 64
    foreground = governor.admit_action("local_model_inference", "sentientosd",
        "foreground-1", {"purpose": "local_user_chat"})
    assert foreground.reason == "deferred_local_model_inference_for_game_frame_pressure"
    assert foreground.evidence_refs["game_performance_evidence"]["message_id"] == "d" * 64
    recovered_observation = VerifiedGamePerformanceObservation(
        "windows-edge", "edge-generation-1", 5, "1" * 64, "2" * 64,
        datetime.now(timezone.utc).isoformat(), "f" * 64, 16.7, 0, 20.0,
        4096, "available")
    assert governor.observe_verified_game_performance(recovered_observation)
    recovered = governor.admit_action("local_model_inference", "sentientosd",
        "background-1", {"purpose": "maintenance_summary"})
    assert recovered.reason == "allowed"
    assert recovered.evidence_refs["game_frame_pressure"] is False
    recovered_chat = governor.admit_action("local_model_inference", "sentientosd",
        "foreground-1", {"purpose": "local_user_chat"})
    assert recovered_chat.reason == "allowed"

    governor._host_resource_evidence = None
    missing_core = governor.admit_action("local_model_inference", "sentientosd",
        "background-2", {"purpose": "maintenance_summary"})
    assert missing_core.reason == "deferred_resource_telemetry_incomplete"


def test_active_game_defers_optional_chat_when_host_resource_sample_is_missing(
        tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    observation = VerifiedGamePerformanceObservation(
        "windows-edge", "edge-generation-1", 1, "a" * 64, "b" * 64,
        datetime.now(timezone.utc).isoformat(), "c" * 64,
        16.7, 0, 18.0, 4096, "available")

    assert governor.observe_verified_game_performance(observation)
    decision = governor.admit_action("local_model_inference", "chat_service",
        "game-without-host-sample", {"purpose": "local_user_chat"})

    assert decision.allowed is False
    assert decision.reason == "deferred_resource_telemetry_incomplete_during_game"
    assert decision.evidence_refs["game_performance_evidence"]["status"] == "current"
    assert decision.evidence_refs["host_resource_evidence"]["status"] == "unavailable"
