from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import threading

import pytest

from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
from sentientos.gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
)
from sentientos.perception.screen_ocr import ScreenCaptureError, ScreenConfig, ScreenOCR

from sentientos.screen_observation_bridge import (
    BridgeScreenObservationProvider,
    RequestDrivenScreenObservation,
    ScreenCaptureRequestSender,
    ScreenObservationBridgeError,
    WindowsScreenObservationBridgePublisher,
)

pytestmark = pytest.mark.no_legacy_skip

SOURCE_KEY = b"windows-screen-source-key-material-32-bytes"
CORE_KEY = b"sentientos-screen-core-key-material-32-bytes"
SOURCE_ID = "windows-screen"
SOURCE_GENERATION = "windows-screen-generation-1"
NOW = datetime.now(timezone.utc)


def _payload(*, captured_at: datetime | None = None) -> dict[str, object]:
    captured_at = datetime.now(timezone.utc) if captured_at is None else captured_at
    return {
        "modality": "screen",
        "text": "quest objective: find the observatory",
        "text_status": "available",
        "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
        "backend": "local-ocr-fixture",
        "capture_digest": "a" * 64,
        "process_name_digest": "b" * 64,
        "consent_id_digest": "c" * 64,
        "capture_scope": "allowlisted_foreground_game_client_area",
        "raw_frame_retained": False,
        "text_truncated": False,
        "text_change_kind": "initial",
        "previous_text_digest": None,
        "visual_change_kind": "initial",
        "visual_change_score": None,
    }


def _setup(*, queue_capacity: int = 2, provider_clock=None):
    runtime = CompanionBridgeLoopbackRuntime(
        receiver=CompanionBridgeReceiver(
            source_keys={SOURCE_ID: SOURCE_KEY},
            expected_generations={SOURCE_ID: SOURCE_GENERATION}),
        acknowledgment_source_id="sentientos-screen-core",
        acknowledgment_generation_id="screen-core-generation-1",
        acknowledgment_key=CORE_KEY, queue_capacity=queue_capacity)
    port = runtime.start()
    client = CompanionBridgeLoopbackClient(port=port,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"sentientos-screen-core": CORE_KEY},
            expected_generations={"sentientos-screen-core": "screen-core-generation-1"}),
        timeout_seconds=1)
    provider = BridgeScreenObservationProvider(runtime=runtime, source_id=SOURCE_ID,
        generation_id=SOURCE_GENERATION, clock=provider_clock,
        max_observation_age_seconds=5)
    return runtime, client, provider


def test_screen_ocr_observation_crosses_authenticated_bridge_as_bounded_text():
    runtime, client, provider = _setup()
    try:
        publisher = WindowsScreenObservationBridgePublisher(
            observe=_payload, client=client, source_id=SOURCE_ID,
            session_id="screen-session-1", generation_id=SOURCE_GENERATION,
            source_key=SOURCE_KEY)
        acknowledgment = publisher.publish_once()
        assert acknowledgment is not None
        assert acknowledgment.payload["disposition"] == "accepted"

        observed = provider()
        assert observed["schema_version"] == "sentientos.game_screen_observation:v6"
        assert observed["text"] == "quest objective: find the observatory"
        assert observed["raw_frame_retained"] is False
        assert "rgb" not in observed
        provenance = observed["bridge_message_provenance"]
        assert provenance["source_id"] == SOURCE_ID
        assert provenance["generation_id"] == SOURCE_GENERATION
        assert provenance["sequence"] == 1
        assert len(provenance["message_id"]) == 64
        assert len(provenance["payload_digest"]) == 64
    finally:
        runtime.close()


def test_slow_vision_result_keeps_capture_time_but_uses_fresh_bridge_timestamp():
    runtime, client, _provider = _setup()
    captured_at = datetime.now(timezone.utc) - timedelta(seconds=60)
    try:
        publisher = WindowsScreenObservationBridgePublisher(
            observe=lambda: _payload(captured_at=captured_at), client=client,
            source_id=SOURCE_ID, session_id="screen-session-1",
            generation_id=SOURCE_GENERATION, source_key=SOURCE_KEY)
        acknowledgment = publisher.publish_once()
        assert acknowledgment is not None
        assert acknowledgment.payload["disposition"] == "accepted"

        observed = runtime.receive(timeout=1)
        assert observed.created_at > captured_at.isoformat().replace("+00:00", "Z")
        assert observed.payload["captured_at"] == captured_at.isoformat().replace("+00:00", "Z")
    finally:
        runtime.close()


def test_component_statuses_cross_authenticated_bridge_without_screen_text_retention():
    runtime, client, provider = _setup()
    observation = _payload()
    observation["backend"] = "tesseract+local_vision"
    observation["component_statuses"] = {
        "ocr": "unavailable", "vision": "available"}
    observation["component_failure_codes"] = {
        "ocr": "game_screen_ocr_backend_unavailable"}
    try:
        publisher = WindowsScreenObservationBridgePublisher(
            observe=lambda: observation, client=client, source_id=SOURCE_ID,
            session_id="screen-session-1", generation_id=SOURCE_GENERATION,
            source_key=SOURCE_KEY)
        assert publisher.publish_once() is not None
        observed = provider()
        assert observed["component_statuses"] == {
            "ocr": "unavailable", "vision": "available"}
        assert observed["component_failure_codes"] == {
            "ocr": "game_screen_ocr_backend_unavailable"}
        assert observed["raw_frame_retained"] is False
        assert "rgb" not in observed
    finally:
        runtime.close()


def test_initial_empty_screen_ocr_result_crosses_authenticated_bridge():
    runtime, client, provider = _setup()
    owner = ScreenOCR(
        ScreenConfig(enable=True, interval_s=0),
        capture_fn=lambda: {
            "rgb": b"\x00\x00\x00", "width": 1, "height": 1,
            "capture_digest": "a" * 64,
            "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "capture_scope": "allowlisted_foreground_game_client_area",
            "process_name_digest": "b" * 64, "consent_id_digest": "c" * 64,
        },
        ocr_fn=lambda _payload: "",
    )
    try:
        publisher = WindowsScreenObservationBridgePublisher(
            observe=owner.snapshot, client=client, source_id=SOURCE_ID,
            session_id="screen-session-1", generation_id=SOURCE_GENERATION,
            source_key=SOURCE_KEY)
        assert publisher.publish_once() is not None
        observed = provider()
        assert observed["text_status"] == "no_readable_text"
        assert observed["previous_text_digest"] is None
        assert observed["raw_frame_retained"] is False
    finally:
        runtime.close()


def test_empty_ocr_is_a_valid_explicit_no_readable_text_observation():
    runtime, client, provider = _setup()
    observation = _payload()
    observation["text"] = ""
    observation["text_status"] = "no_readable_text"
    try:
        publisher = WindowsScreenObservationBridgePublisher(
            observe=lambda: observation, client=client, source_id=SOURCE_ID,
            session_id="screen-session-1", generation_id=SOURCE_GENERATION,
            source_key=SOURCE_KEY)
        assert publisher.publish_once() is not None
        observed = provider()
        assert observed["text"] == ""
        assert observed["text_status"] == "no_readable_text"
        assert observed["raw_frame_retained"] is False
    finally:
        runtime.close()


@pytest.mark.parametrize("changes, code", [
    ({"text": " "}, "screen_observation_contract_invalid"),
    ({"text_status": "no_readable_text"}, "screen_observation_contract_invalid"),
    ({"text": "", "text_status": "available"}, "screen_observation_contract_invalid"),
    ({"text": "x" * 1201}, "screen_observation_contract_invalid"),
    ({"raw_frame_retained": True}, "screen_observation_contract_invalid"),
    ({"text_change_kind": "visual_event"}, "screen_observation_contract_invalid"),
    ({"text_change_kind": "changed", "previous_text_digest": None},
     "screen_observation_change_lineage_invalid"),
    ({"text_change_kind": "changed",
      "previous_text_digest": hashlib.sha256(
          b"quest objective: find the observatory").hexdigest()},
     "screen_observation_change_lineage_invalid"),
    ({"capture_digest": "not-a-digest"}, "screen_observation_digest_invalid"),
    ({"visual_change_kind": "event_detected", "visual_change_score": 0.5},
     "screen_observation_contract_invalid"),
    ({"visual_change_score": 1.5}, "screen_observation_contract_invalid"),
    ({"component_statuses": {"vision": "maybe"}},
     "screen_observation_component_status_invalid"),
    ({"component_failure_codes": {"vision": "game_screen_vision_timeout"}},
     "screen_observation_component_failure_invalid"),
    ({"backend": "tesseract+local_vision",
      "component_statuses": {"vision": "available"}},
     "screen_observation_component_status_invalid"),
    ({"capture_request_id": "invalid"}, "screen_observation_request_id_invalid"),
    ({"unexpected": "field"}, "screen_observation_shape_invalid"),
])
def test_publisher_rejects_invalid_or_unbounded_observation(changes, code):
    runtime, client, _provider = _setup()
    observation = _payload()
    observation.update(changes)
    try:
        publisher = WindowsScreenObservationBridgePublisher(
            observe=lambda: observation, client=client, source_id=SOURCE_ID,
            session_id="screen-session-1", generation_id=SOURCE_GENERATION,
            source_key=SOURCE_KEY)
        with pytest.raises(ScreenObservationBridgeError, match=code):
            publisher.publish_once()
    finally:
        runtime.close()



def test_request_driven_capture_publishes_only_the_matching_message_observation():
    runtime, observation_client, provider = _setup()
    request_key = b"screen-request-key-material-32-bytes"
    request_ack_key = b"screen-request-ack-key-material-32-bytes"
    request_runtime = CompanionBridgeLoopbackRuntime(
        receiver=CompanionBridgeReceiver(
            source_keys={"wsl-screen-request": request_key},
            expected_generations={"wsl-screen-request": "screen-request-generation-1"}),
        acknowledgment_source_id="windows-screen-request-ack",
        acknowledgment_generation_id="windows-screen-request-ack-generation-1",
        acknowledgment_key=request_ack_key)
    request_port = request_runtime.start()
    request_client = CompanionBridgeLoopbackClient(
        port=request_port,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"windows-screen-request-ack": request_ack_key},
            expected_generations={"windows-screen-request-ack":
                                  "windows-screen-request-ack-generation-1"}),
        timeout_seconds=1)
    request_sender = ScreenCaptureRequestSender(
        client=request_client, source_id="wsl-screen-request",
        session_id="wsl-screen-session",
        generation_id="screen-request-generation-1", source_key=request_key)
    capture_calls = []
    samples = [
        "Quest\nOld screen",
        "Quest\nFind the key",
        "Quest\nOpen the gate",
        "Visual summary (local model): armored figure beside stained glass",
    ]
    backends = [
        "local-ocr-fixture", "local-ocr-fixture", "local-ocr-fixture",
        "tesseract+local_vision",
    ]
    previous_text = []
    def capture_once():
        capture_calls.append(True)
        observation = _payload()
        sample_index = len(capture_calls) - 1
        observation["text"] = samples.pop(0)
        observation["backend"] = backends[sample_index]
        observation["text_change_kind"] = "initial" if not previous_text else "changed"
        observation["previous_text_digest"] = (
            None if not previous_text else hashlib.sha256(
                previous_text[-1].encode("utf-8")).hexdigest())
        previous_text.append(observation["text"])
        return observation

    publisher = WindowsScreenObservationBridgePublisher(
        observe=capture_once,
        client=observation_client, source_id=SOURCE_ID,
        session_id="screen-session-1", generation_id=SOURCE_GENERATION,
        source_key=SOURCE_KEY)
    stale_request_id = "a" * 32
    assert publisher.publish_once(capture_request_id=stale_request_id) is not None
    failures = []

    def capture_requests():
        try:
            for _ in range(3):
                request = request_runtime.receive(timeout=2)
                assert request.kind == "screen_capture_request"
                publisher.publish_once(
                    capture_request_id=request.payload["capture_request_id"])
        except Exception as exc:
            failures.append(exc)

    worker = threading.Thread(target=capture_requests)
    worker.start()
    request_driven = RequestDrivenScreenObservation(
        request_sender=request_sender, provider=provider, timeout_seconds=0.1,
        consent_expires_at="2099-01-01T00:00:00Z",
        foreground_wait_seconds=5.0)
    assert request_driven.consent_status()["consent_status"] == "active"
    assert request_driven.consent_status()["foreground_wait_seconds"] == 5.0
    expired_observer = RequestDrivenScreenObservation(
        request_sender=request_sender, provider=provider, timeout_seconds=0.1,
        consent_expires_at="2000-01-01T00:00:00Z")
    assert expired_observer.consent_status()["consent_status"] == "expired"
    try:
        observed = request_driven()
        assert not failures
        assert len(capture_calls) == 2
        first_request_id = observed["capture_request_id"]
        assert first_request_id and first_request_id != stale_request_id
        assert observed["text"] == "Quest\nFind the key"
        freshness = observed["capture_freshness"]
        assert freshness["basis"] == "request_correlated_monotonic_upper_bound"
        assert freshness["capture_request_id"] == first_request_id
        assert freshness["capture_age_upper_bound_ms"] <= 100
        changed = request_driven()
        assert len(capture_calls) == 3
        assert changed["capture_request_id"] != first_request_id
        assert changed["text"] == "Quest\nOpen the gate"
        assert changed["text_delta"]["added_lines"] == ["Open the gate"]
        assert changed["text_delta"]["removed_lines"] == ["Find the key"]
        vision = request_driven()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert vision["backend"] == "tesseract+local_vision"
        assert vision["text"].startswith("Visual summary (local model):")
        assert "text_delta" not in vision
        assert len(capture_calls) == 4
        with pytest.raises(ScreenObservationBridgeError,
                           match="screen_observation_request_timeout"):
            request_driven()
    finally:
        request_driven.close()
        request_runtime.close()
        runtime.close()


def test_request_bound_capture_uses_monotonic_deadline_across_host_clock_skew():
    # Model a WSL clock 20 seconds ahead of the capture host. The signed
    # observation is still bound to this newly generated request ID.
    runtime, observation_client, provider = _setup(
        provider_clock=lambda: NOW + timedelta(seconds=20))
    request_key = b"screen-request-key-material-32-bytes"
    request_ack_key = b"screen-request-ack-key-material-32-bytes"
    request_runtime = CompanionBridgeLoopbackRuntime(
        receiver=CompanionBridgeReceiver(
            source_keys={"wsl-screen-request": request_key},
            expected_generations={"wsl-screen-request": "screen-request-generation-1"}),
        acknowledgment_source_id="windows-screen-request-ack",
        acknowledgment_generation_id="windows-screen-request-ack-generation-1",
        acknowledgment_key=request_ack_key)
    request_port = request_runtime.start()
    request_client = CompanionBridgeLoopbackClient(
        port=request_port,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"windows-screen-request-ack": request_ack_key},
            expected_generations={"windows-screen-request-ack":
                                  "windows-screen-request-ack-generation-1"}),
        timeout_seconds=1)
    request_sender = ScreenCaptureRequestSender(
        client=request_client, source_id="wsl-screen-request",
        session_id="wsl-screen-session",
        generation_id="screen-request-generation-1", source_key=request_key)
    questions = []
    publisher = WindowsScreenObservationBridgePublisher(
        observe=_payload,
        observe_question=lambda question: (questions.append(question) or _payload()),
        client=observation_client, source_id=SOURCE_ID,
        session_id="screen-session-1", generation_id=SOURCE_GENERATION,
        source_key=SOURCE_KEY)
    failures = []

    def capture_request():
        try:
            request = request_runtime.receive(timeout=2)
            publisher.publish_once(
                capture_request_id=request.payload["capture_request_id"],
                question=request.payload.get("question"))
        except Exception as exc:
            failures.append(exc)

    worker = threading.Thread(target=capture_request)
    worker.start()
    request_driven = RequestDrivenScreenObservation(
        request_sender=request_sender, provider=provider, timeout_seconds=1)
    try:
        question = "How many candles are visible?"
        observed = request_driven(question)
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert not failures
        assert observed["capture_request_id"]
        assert observed["text"] == "quest objective: find the observatory"
        assert questions == [question]
        assert "question" not in observed
    finally:
        request_driven.close()
        request_runtime.close()
        runtime.close()


def test_request_driven_capture_failure_returns_specific_code_without_waiting_for_timeout():
    runtime, observation_client, provider = _setup()
    request_key = b"screen-request-key-material-32-bytes"
    request_ack_key = b"screen-request-ack-key-material-32-bytes"
    request_runtime = CompanionBridgeLoopbackRuntime(
        receiver=CompanionBridgeReceiver(
            source_keys={"wsl-screen-request": request_key},
            expected_generations={"wsl-screen-request": "screen-request-generation-1"}),
        acknowledgment_source_id="windows-screen-request-ack",
        acknowledgment_generation_id="windows-screen-request-ack-generation-1",
        acknowledgment_key=request_ack_key)
    request_port = request_runtime.start()
    request_sender = ScreenCaptureRequestSender(
        client=CompanionBridgeLoopbackClient(
            port=request_port,
            acknowledgment_receiver=CompanionBridgeReceiver(
                source_keys={"windows-screen-request-ack": request_ack_key},
                expected_generations={"windows-screen-request-ack":
                                      "windows-screen-request-ack-generation-1"}),
            timeout_seconds=1),
        source_id="wsl-screen-request", session_id="wsl-screen-session",
        generation_id="screen-request-generation-1", source_key=request_key)
    def fail_capture():
        raise ScreenCaptureError("game_screen_foreground_process_not_allowlisted")

    publisher = WindowsScreenObservationBridgePublisher(
        observe=fail_capture, client=observation_client, source_id=SOURCE_ID,
        session_id="screen-session-1", generation_id=SOURCE_GENERATION,
        source_key=SOURCE_KEY)
    failures = []

    def report_capture_failure():
        try:
            request = request_runtime.receive(timeout=2)
            publisher.publish_request(request.payload["capture_request_id"])
        except ScreenCaptureError as exc:
            if exc.args != ("game_screen_foreground_process_not_allowlisted",):
                failures.append(exc)
        except Exception as exc:
            failures.append(exc)

    worker = threading.Thread(target=report_capture_failure)
    worker.start()
    request_driven = RequestDrivenScreenObservation(
        request_sender=request_sender, provider=provider, timeout_seconds=2)
    try:
        observed_error = None
        try:
            request_driven()
        except ScreenObservationBridgeError as exc:
            observed_error = exc
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert not failures
        assert observed_error is not None
        assert observed_error.args == (
            "game_screen_foreground_process_not_allowlisted",)
    finally:
        request_driven.close()
        request_runtime.close()
        runtime.close()


def test_provider_rejects_stale_screen_observation_after_authenticated_transport():
    runtime, client, provider = _setup()
    try:
        stale = _payload(captured_at=NOW - timedelta(seconds=10))
        publisher = WindowsScreenObservationBridgePublisher(
            observe=lambda: stale, client=client, source_id=SOURCE_ID,
            session_id="screen-session-1", generation_id=SOURCE_GENERATION,
            source_key=SOURCE_KEY)
        assert publisher.publish_once() is not None
        with pytest.raises(ScreenObservationBridgeError, match="screen_observation_expired"):
            provider()
    finally:
        runtime.close()


def test_provider_fails_closed_when_no_consent_scoped_observation_arrived():
    runtime, _client, provider = _setup()
    try:
        with pytest.raises(ScreenObservationBridgeError,
                           match="screen_observation_unavailable"):
            provider()
    finally:
        runtime.close()


def test_disabled_or_duplicate_capture_does_not_publish_a_message():
    runtime, client, provider = _setup()
    try:
        publisher = WindowsScreenObservationBridgePublisher(
            observe=lambda: None, client=client, source_id=SOURCE_ID,
            session_id="screen-session-1", generation_id=SOURCE_GENERATION,
            source_key=SOURCE_KEY)
        assert publisher.publish_once() is None
        with pytest.raises(ScreenObservationBridgeError,
                           match="screen_observation_unavailable"):
            provider()
    finally:
        runtime.close()
