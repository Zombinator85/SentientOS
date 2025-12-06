from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Dict

import pytest

from sentientos.daemons import pulse_bus


def test_apply_defaults_is_deterministic() -> None:
    base_event: Dict[str, object] = {
        "timestamp": "2024-01-01T00:00:00Z",
        "source_daemon": "tester",
        "event_type": "unit",
        "payload": {"value": 1},
    }

    first = pulse_bus.apply_pulse_defaults(copy.deepcopy(base_event))
    second = pulse_bus.apply_pulse_defaults(copy.deepcopy(base_event))

    assert first == second
    assert first["focus"] is None
    assert first["context"] == {}
    assert first["internal_priority"] == "baseline"
    assert first["event_origin"] == "local"


def test_normalize_rejects_invalid_schema(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("PULSE_HISTORY_ROOT", str(tmp_path / "history"))
    bus = pulse_bus._PulseBus()

    event: Dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "tester",
        "event_type": "unit",
        "payload": {},
        "context": "not-a-dict",
    }

    with pytest.raises(TypeError):
        bus._normalize_event(event)


def test_publish_rejects_invalid_event_before_delivery(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("PULSE_HISTORY_ROOT", str(tmp_path / "history"))
    monkeypatch.setattr(pulse_bus._SIGNATURE_MANAGER, "sign", lambda evt: "sig")
    bus = pulse_bus._PulseBus()

    bad_event: Dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_daemon": "tester",
        "event_type": "unit",
        "payload": {"value": 2},
        "focus": 123,
    }

    with pytest.raises(TypeError):
        bus.publish(bad_event)


def test_normalize_retains_schema_fields(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("PULSE_HISTORY_ROOT", str(tmp_path / "history"))
    bus = pulse_bus._PulseBus()

    event: Dict[str, object] = {
        "timestamp": "2024-02-02T00:00:00Z",
        "source_daemon": "tester",
        "event_type": "unit",
        "payload": {"value": 3},
        "focus": "preserve-me",
        "context": {"note": "ok"},
        "internal_priority": 0.5,
        "event_origin": "peer",
    }

    normalized = bus._normalize_event(event)

    assert normalized["focus"] == "preserve-me"
    assert normalized["context"] == {"note": "ok"}
    assert normalized["internal_priority"] == 0.5
    assert normalized["event_origin"] == "peer"
    assert normalized["priority"] == "info"
