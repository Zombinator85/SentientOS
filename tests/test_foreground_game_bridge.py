from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from threading import Lock

import pytest

from sentientos.foreground_game_bridge import (
    BridgeForegroundGameDetector,
    WindowsForegroundBridgePublisher,
)
from sentientos.foreground_game_detection import ForegroundGameObservation
from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
from sentientos.gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
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
        "available", False, hashlib.sha256(b"desktop.exe").hexdigest(), STAMP))
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
