from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from threading import Event, Lock
import time

import pytest

from sentientos.foreground_game_bridge import (
    BridgeForegroundGameDetector,
    WindowsForegroundObservationPump,
    WindowsForegroundBridgePublisher,
)
from sentientos.foreground_game_detection import ForegroundGameObservation
from sentientos.gaming_companion_bridge import CompanionBridgeError, CompanionBridgeReceiver
from sentientos.gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
    CompanionBridgeTransportError,
)
from sentientos.local_model_serving_inference import ProductionServingInferenceController

pytestmark = pytest.mark.no_legacy_skip

SOURCE_KEY = b"windows-foreground-test-key-material-32-bytes"
CORE_KEY = b"sentientos-core-test-key-material-32-bytes"
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
STAMP = NOW.isoformat()
SOURCE_ID = "windows-foreground"
SOURCE_GENERATION = "windows-observer-generation-1"


class LocalObservation:
    def __init__(self, observation: ForegroundGameObservation) -> None:
        self.observation = observation

    def observe(self, _process_names):
        return self.observation


def _runtime() -> CompanionBridgeLoopbackRuntime:
    receiver = CompanionBridgeReceiver(
        source_keys={SOURCE_ID: SOURCE_KEY},
        expected_generations={SOURCE_ID: SOURCE_GENERATION},
        clock=lambda: NOW.timestamp(),
    )
    return CompanionBridgeLoopbackRuntime(
        receiver=receiver,
        acknowledgment_source_id="sentientos-core",
        acknowledgment_generation_id="core-generation-1",
        acknowledgment_key=CORE_KEY,
        queue_capacity=4,
        clock=lambda: NOW,
    )


def _publish(observation: ForegroundGameObservation):
    runtime = _runtime()
    port = runtime.start()
    acknowledgment_receiver = CompanionBridgeReceiver(
        source_keys={"sentientos-core": CORE_KEY},
        expected_generations={"sentientos-core": "core-generation-1"},
        clock=lambda: NOW.timestamp(),
    )
    client = CompanionBridgeLoopbackClient(port=port,
        acknowledgment_receiver=acknowledgment_receiver, timeout_seconds=0.5)
    publisher = WindowsForegroundBridgePublisher(
        detector=LocalObservation(observation), client=client,
        source_id=SOURCE_ID, session_id="observer-session-1",
        generation_id=SOURCE_GENERATION, source_key=SOURCE_KEY)
    publisher.publish_once(("game.exe",))
    return runtime


def _automatic_controller(detector: BridgeForegroundGameDetector):
    controller = object.__new__(ProductionServingInferenceController)
    controller._workload_lock = Lock()
    controller._workload_mode = "normal"
    controller._game_process_names = ()
    controller._foreground_game_detector = detector
    controller.set_workload_mode("automatic", ("game.exe",))
    return controller


def test_authenticated_windows_sample_drives_existing_automatic_workload_decision():
    runtime = _publish(ForegroundGameObservation(
        "available", True, hashlib.sha256(b"game.exe").hexdigest(), STAMP))
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=SOURCE_ID,
        generation_id=SOURCE_GENERATION, clock=lambda: NOW, max_observation_age_seconds=5)
    controller = _automatic_controller(detector)
    try:
        state = controller.current_workload_state()
        assert state["effective_mode"] == "gaming"
        assert state["mode_source"] == "foreground_allowlist_match"
        assert state["transport_provenance"]["source_id"] == SOURCE_ID
        assert state["transport_provenance"]["generation_id"] == SOURCE_GENERATION
        assert state["transport_provenance"]["sequence"] == 1
        assert state["transport_provenance"]["message_id"]
    finally:
        detector.close()


def test_non_game_observation_returns_to_normal_and_preserves_source_lineage():
    runtime = _publish(ForegroundGameObservation(
        "available", False, hashlib.sha256(b"desktop.exe").hexdigest(), STAMP,
        game_process_running=False, running_process_name_digests=()))
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=SOURCE_ID,
        generation_id=SOURCE_GENERATION, clock=lambda: NOW)
    controller = _automatic_controller(detector)
    try:
        state = controller.current_workload_state()
        assert state["effective_mode"] == "normal"
        assert state["mode_source"] == "foreground_allowlist_no_match"
        assert state["transport_provenance"]["sequence"] == 1
    finally:
        detector.close()


def test_stale_observation_fails_into_conservative_gaming_mode():
    stale_stamp = (NOW - timedelta(seconds=10)).isoformat()
    runtime = _publish(ForegroundGameObservation(
        "available", True, hashlib.sha256(b"game.exe").hexdigest(), stale_stamp))
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=SOURCE_ID,
        generation_id=SOURCE_GENERATION, clock=lambda: NOW, max_observation_age_seconds=5)
    controller = _automatic_controller(detector)
    try:
        state = controller.current_workload_state()
        assert state["effective_mode"] == "gaming"
        assert state["mode_source"] == "foreground_observation_unavailable_conservative_gaming"
        assert state["observation_status"] == "bridge_observation_expired"
        assert state["transport_provenance"] is None
    finally:
        detector.close()


def test_missing_bridge_sample_fails_into_conservative_gaming_mode():
    runtime = _runtime()
    runtime.start()
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=SOURCE_ID,
        generation_id=SOURCE_GENERATION, clock=lambda: NOW)
    controller = _automatic_controller(detector)
    try:
        state = controller.current_workload_state()
        assert state["effective_mode"] == "gaming"
        assert state["observation_status"] == "bridge_observation_unavailable"
    finally:
        detector.close()


def test_sender_cannot_claim_an_allowlisted_game_with_an_unlisted_digest():
    runtime = _publish(ForegroundGameObservation(
        "available", True, hashlib.sha256(b"desktop.exe").hexdigest(), STAMP))
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=SOURCE_ID,
        generation_id=SOURCE_GENERATION, clock=lambda: NOW)
    try:
        observation = detector.observe(("game.exe",))
        assert observation.status == "bridge_observation_invalid"
        assert observation.game_foreground is None
        assert observation.transport_provenance is None
    finally:
        detector.close()


def test_observation_pump_sends_fresh_samples_and_has_a_one_shot_lifecycle():
    runtime = _runtime()
    port = runtime.start()
    acknowledgments = CompanionBridgeReceiver(
        source_keys={"sentientos-core": CORE_KEY},
        expected_generations={"sentientos-core": "core-generation-1"},
        clock=lambda: NOW.timestamp(),
    )
    client = CompanionBridgeLoopbackClient(port=port,
        acknowledgment_receiver=acknowledgments, timeout_seconds=0.5)
    sample_ready = Event()

    class RepeatedObservation:
        def observe(self, _process_names):
            sample_ready.set()
            return ForegroundGameObservation(
                "available", True, hashlib.sha256(b"game.exe").hexdigest(), STAMP)

    publisher = WindowsForegroundBridgePublisher(
        detector=RepeatedObservation(), client=client, source_id=SOURCE_ID,
        session_id="observer-session-1", generation_id=SOURCE_GENERATION,
        source_key=SOURCE_KEY)
    pump = WindowsForegroundObservationPump(
        publisher=publisher, process_names=("game.exe",), interval_seconds=0.1)
    try:
        pump.start()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and pump.status().acknowledgments < 2:
            sample_ready.wait(0.05)
        pump.close()
        status = pump.status()
        assert not status.running
        assert status.attempts >= 2
        assert status.acknowledgments >= 2
        assert status.failures == 0
        assert status.last_message_id
        assert status.last_delivery_state == "accepted"

        accepted = []
        while True:
            try:
                accepted.append(runtime.receive(timeout=0))
            except CompanionBridgeError as exc:
                assert exc.args == ("bridge_receive_timeout",)
                break
        assert len(accepted) >= 2
        assert [message.sequence for message in accepted] == sorted(
            message.sequence for message in accepted)
        with pytest.raises(CompanionBridgeError, match="generation_rotation_required"):
            pump.start()
    finally:
        pump.close()
        runtime.close()


def test_pump_takes_a_new_sample_after_indeterminate_delivery_instead_of_replaying():
    runtime = _runtime()
    port = runtime.start()
    acknowledgments = CompanionBridgeReceiver(
        source_keys={"sentientos-core": CORE_KEY},
        expected_generations={"sentientos-core": "core-generation-1"},
        clock=lambda: NOW.timestamp(),
    )

    class IndeterminateOnceClient(CompanionBridgeLoopbackClient):
        def __init__(self):
            super().__init__(port=port, acknowledgment_receiver=acknowledgments,
                timeout_seconds=0.5)
            self.frames = []

        def send(self, encoded):
            self.frames.append(encoded)
            if len(self.frames) == 1:
                raise CompanionBridgeTransportError("bridge_delivery_indeterminate",
                    delivery_state="indeterminate")
            return super().send(encoded)

    class ChangingObservation:
        def __init__(self):
            self.calls = 0

        def observe(self, _process_names):
            self.calls += 1
            name = "game.exe" if self.calls == 1 else "desktop.exe"
            return ForegroundGameObservation("available", name == "game.exe",
                hashlib.sha256(name.encode()).hexdigest(), STAMP)

    client = IndeterminateOnceClient()
    publisher = WindowsForegroundBridgePublisher(
        detector=ChangingObservation(), client=client, source_id=SOURCE_ID,
        session_id="observer-session-1", generation_id=SOURCE_GENERATION,
        source_key=SOURCE_KEY)
    pump = WindowsForegroundObservationPump(
        publisher=publisher, process_names=("game.exe",), interval_seconds=0.1)
    try:
        pump.start()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            state = pump.status()
            if state.failures >= 1 and state.acknowledgments >= 1:
                break
            time.sleep(0.01)
        pump.close()
        status = pump.status()
        assert status.last_failure_code == "bridge_delivery_indeterminate"
        assert status.last_failure_delivery_state == "indeterminate"
        assert status.last_failure_at
        assert status.last_delivery_state == "accepted"
        assert status.failures >= 1
        assert status.acknowledgments >= 1
        assert client.frames[0] != client.frames[1]
        first, second = (json.loads(frame) for frame in client.frames[:2])
        assert first["sequence"] == 1
        assert second["sequence"] == 2
        assert first["payload"]["process_name_digest"] != second["payload"]["process_name_digest"]
        received = runtime.receive(timeout=0.5)
        assert received.sequence == 2
    finally:
        pump.close()
        runtime.close()


def test_authenticated_background_game_presence_keeps_automatic_workload_game_safe():
    digest = hashlib.sha256(b"game.exe").hexdigest()
    runtime = _publish(ForegroundGameObservation(
        "available", False, hashlib.sha256(b"desktop.exe").hexdigest(), STAMP,
        game_process_running=True, running_process_name_digests=(digest,)))
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=SOURCE_ID,
        generation_id=SOURCE_GENERATION, clock=lambda: NOW)
    controller = _automatic_controller(detector)
    try:
        state = controller.current_workload_state()
        assert state["game_foreground"] is False
        assert state["game_process_running"] is True
        assert state["effective_mode"] == "gaming"
        assert state["mode_source"] == "allowlisted_game_process_running"
        assert state["running_process_name_digests"] == [digest]
    finally:
        detector.close()


def test_authenticated_background_game_digest_must_match_allowlist():
    runtime = _publish(ForegroundGameObservation(
        "available", False, hashlib.sha256(b"desktop.exe").hexdigest(), STAMP,
        game_process_running=True,
        running_process_name_digests=(hashlib.sha256(b"other.exe").hexdigest(),)))
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=SOURCE_ID,
        generation_id=SOURCE_GENERATION, clock=lambda: NOW)
    try:
        observation = detector.observe(("game.exe",))
        assert observation.status == "bridge_observation_invalid"
        assert observation.game_process_running is None
    finally:
        detector.close()
