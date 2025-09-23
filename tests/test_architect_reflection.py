import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import pytest

import architect_daemon
from sentientos.daemons import pulse_bus


class TestClock:
    def __init__(self, current: datetime) -> None:
        self._current = current

    def now(self) -> datetime:
        return self._current

    def set(self, new_time: datetime) -> None:
        self._current = new_time


@pytest.fixture(autouse=True)
def reset_pulse_bus() -> None:
    pulse_bus.reset()
    yield
    pulse_bus.reset()


def _create_daemon(
    tmp_path: Path,
    *,
    reflection_interval: int = 2,
    ledger_events: list[dict[str, object]] | None = None,
    config: Mapping[str, object] | None = None,
    monkeypatch: pytest.MonkeyPatch,
) -> architect_daemon.ArchitectDaemon:
    monkeypatch.setattr(architect_daemon.codex_daemon, "load_ethics", lambda: "")

    request_dir = tmp_path / "requests"
    session_file = tmp_path / "session.json"
    ledger_path = tmp_path / "ledger.jsonl"
    config_path = tmp_path / "config.yaml"
    reflection_dir = tmp_path / "reflections"
    reflection_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(config or {})
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    completion_path = tmp_path / "vow" / "first_boot_complete"
    completion_path.parent.mkdir(parents=True, exist_ok=True)
    completion_path.write_text("done", encoding="utf-8")

    clock = TestClock(datetime(2025, 1, 1, tzinfo=timezone.utc))
    ledger_sink = ledger_events.append if ledger_events is not None else lambda event: event

    daemon = architect_daemon.ArchitectDaemon(
        request_dir=request_dir,
        session_file=session_file,
        ledger_path=ledger_path,
        config_path=config_path,
        completion_path=completion_path,
        reflection_dir=reflection_dir,
        reflection_interval=reflection_interval,
        clock=clock.now,
        ledger_sink=ledger_sink,
        pulse_publisher=pulse_bus.publish,
        ci_commands=[["true"]],
        immutability_command=["true"],
    )
    daemon.start()
    return daemon


def test_reflection_cycle_saves_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_events: list[dict[str, object]] = []
    daemon = _create_daemon(
        tmp_path,
        reflection_interval=2,
        ledger_events=ledger_events,
        monkeypatch=monkeypatch,
    )
    daemon._cycle_counter = daemon._reflection_interval - 1

    pulses: list[dict[str, object]] = []
    pulse_bus.subscribe(lambda event: pulses.append(event))

    request = daemon._begin_cycle(trigger="scheduled", timestamp=daemon._now())
    assert request is not None and request.mode == "reflect"

    assert any(
        event["event_type"] == "architect_reflection_start" for event in pulses
    )

    reflection_payload = {
        "summary": "Cycles stable",
        "successes": ["Green tests"],
        "failures": [],
        "regressions": [],
        "next_priorities": ["Harden monitoring"]
    }
    entry = {
        "event": "self_reflection",
        "request_id": request.codex_prefix + "result",
        "reflection": json.dumps(reflection_payload),
    }
    daemon.handle_ledger_entry(entry)

    reflection_files = sorted((tmp_path / "reflections").glob("reflection_*.json"))
    assert reflection_files, "reflection file created"
    saved = json.loads(reflection_files[0].read_text(encoding="utf-8"))
    for key in ["summary", "successes", "failures", "regressions", "next_priorities"]:
        assert key in saved
    assert saved["summary"] == "Cycles stable"

    assert any(evt["event"] == "architect_reflection" for evt in ledger_events)
    assert any(
        event["event_type"] == "architect_reflection_complete" for event in pulses
    )
    complete_events = [
        event for event in pulses if event["event_type"] == "architect_reflection_complete"
    ]
    assert complete_events and complete_events[0]["payload"]["next_priorities"] == [
        "Harden monitoring"
    ]
    assert daemon._last_reflection_summary == "Cycles stable"


def test_invalid_reflection_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_events: list[dict[str, object]] = []
    daemon = _create_daemon(
        tmp_path,
        reflection_interval=1,
        ledger_events=ledger_events,
        monkeypatch=monkeypatch,
    )
    pulses: list[dict[str, object]] = []
    pulse_bus.subscribe(lambda event: pulses.append(event))

    request = daemon._begin_cycle(trigger="manual", timestamp=daemon._now())
    assert request is not None and request.mode == "reflect"

    entry = {
        "event": "self_reflection",
        "request_id": request.codex_prefix + "bad",
        "reflection": json.dumps({"summary": "oops"}),
    }
    daemon.handle_ledger_entry(entry)

    assert any(evt["event"] == "architect_reflection_failed" for evt in ledger_events)
    assert any(
        event["event_type"] == "architect_reflection_failed" for event in pulses
    )
    reflection_files = list((tmp_path / "reflections").glob("reflection_*.json"))
    assert not reflection_files


def test_federated_reflection_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_events: list[dict[str, object]] = []
    config = {
        "federate_reflections": True,
        "federation_peer_name": "lighthouse",
        "federation_peers": ["aurora"],
    }
    daemon = _create_daemon(
        tmp_path,
        reflection_interval=1,
        ledger_events=ledger_events,
        config=config,
        monkeypatch=monkeypatch,
    )

    pulses: list[dict[str, object]] = []
    pulse_bus.subscribe(lambda event: pulses.append(event))

    request = daemon._begin_cycle(trigger="scheduled", timestamp=daemon._now())
    assert request is not None and request.mode == "reflect"

    payload = {
        "summary": "Peers ready",
        "successes": [],
        "failures": [],
        "regressions": [],
        "next_priorities": ["Share plans"],
    }
    entry = {
        "event": "self_reflection",
        "request_id": request.codex_prefix + "done",
        "reflection": json.dumps(payload),
    }
    daemon.handle_ledger_entry(entry)

    complete_events = [
        event for event in pulses if event["event_type"] == "architect_reflection_complete"
    ]
    assert complete_events, "complete pulse emitted"
    payload = complete_events[0]["payload"]
    assert payload["federated"] is True
    assert payload["peers"] == ["aurora"]
    assert payload["peer_name"] == "lighthouse"
    ledger_complete = [evt for evt in ledger_events if evt["event"] == "architect_reflection"]
    assert ledger_complete and ledger_complete[0]["federated"] is True

