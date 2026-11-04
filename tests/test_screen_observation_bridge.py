from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
from sentientos.gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
)
from sentientos.screen_observation_bridge import (
    BridgeScreenObservationProvider,
    ScreenObservationBridgeError,
    WindowsScreenObservationBridgePublisher,
)

pytestmark = pytest.mark.no_legacy_skip

SOURCE_KEY = b"windows-screen-source-key-material-32-bytes"
CORE_KEY = b"sentientos-screen-core-key-material-32-bytes"
SOURCE_ID = "windows-screen"
SOURCE_GENERATION = "windows-screen-generation-1"
NOW = datetime.now(timezone.utc)


def _payload(*, captured_at: datetime = NOW) -> dict[str, object]:
    return {
        "modality": "screen",
        "text": "quest objective: find the observatory",
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
    }


def _setup(*, queue_capacity: int = 2):
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
        generation_id=SOURCE_GENERATION, max_observation_age_seconds=5)
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
        assert observed["schema_version"] == "sentientos.game_screen_observation:v2"
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


@pytest.mark.parametrize("changes, code", [
    ({"text": " "}, "screen_observation_contract_invalid"),
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
