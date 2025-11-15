import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from sentientos.federation.drift import DriftReport
from sentientos.federation.poller import FederationState
from sentientos.memory import pulse_view
from sentientos.memory.pulse_view import collect_recent_pulse
from sentientos.persona.state import PersonaState
from sentientos.world.bus import WorldEventBus
from sentientos.world.events import WorldEvent


def _write_jsonl(path: Path, entries: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, sort_keys=True) for entry in entries]
    path.write_text("\n".join(lines), encoding="utf-8")


def test_collect_recent_pulse_gathers_sources(monkeypatch, tmp_path: Path) -> None:
    since = datetime(2024, 3, 10, 12, 0, tzinfo=timezone.utc)

    experiment_log = tmp_path / "experiments.jsonl"
    monkeypatch.setattr(pulse_view, "_EXPERIMENT_CHAIN_PATH", experiment_log)
    _write_jsonl(
        experiment_log,
        [
            {
                "timestamp": (since + timedelta(minutes=1)).isoformat(),
                "chain_id": "chain-1",
                "experiment_id": "exp-1",
                "success": True,
            },
            {
                "timestamp": (since + timedelta(minutes=2)).isoformat(),
                "chain_id": "chain-1",
                "experiment_id": "exp-2",
                "success": False,
                "error": "timeout",
            },
        ],
    )

    cathedral_log = tmp_path / "cathedral.log"
    _write_jsonl(
        cathedral_log,
        [
            {
                "timestamp": (since + timedelta(minutes=3)).isoformat(),
                "amendment_id": "amend-1",
                "status": "accepted",
            },
            {
                "timestamp": (since + timedelta(minutes=4)).isoformat(),
                "amendment_id": "amend-2",
                "status": "quarantined",
            },
        ],
    )

    ledger_log = tmp_path / "ledger.jsonl"
    _write_jsonl(
        ledger_log,
        [
            {
                "ts": (since + timedelta(minutes=5)).isoformat(),
                "event": "rollback",
                "amendment_id": "amend-1",
                "reverted": {"config": "ok"},
            },
            {
                "ts": (since + timedelta(minutes=6)).isoformat(),
                "event": "rollback_error",
                "amendment_id": "amend-3",
                "error": "conflict",
            },
        ],
    )

    bus = WorldEventBus()
    world_event = WorldEvent(
        "system_load",
        since + timedelta(minutes=7),
        "System load high",
        {"level": "high"},
    )
    bus.push(world_event)

    state = FederationState(
        last_poll_ts=since + timedelta(minutes=8),
        peer_reports={"peer-a": DriftReport(peer="peer-a", level="drift", reasons=["digest mismatch"])}
    )

    persona_state = PersonaState()
    persona_state.last_update_ts = since + timedelta(minutes=9)
    persona_state.recent_reflection = "I’ve been careful."

    runtime = SimpleNamespace(
        cathedral_log_path=cathedral_log,
        ledger_path=ledger_log,
        world_bus=bus,
        get_federation_state=lambda: state,
        _persona_loop=SimpleNamespace(state=persona_state),
    )

    pulses = collect_recent_pulse(runtime, since)
    kinds = [event.kind for event in pulses]
    assert kinds == [
        "experiment",
        "experiment",
        "cathedral",
        "cathedral",
        "rollback",
        "rollback",
        "world",
        "federation",
        "persona",
    ]

    severities = [event.severity for event in pulses]
    assert severities == [
        "info",
        "error",
        "info",
        "warn",
        "info",
        "error",
        "warn",
        "warn",
        "info",
    ]

    assert pulses[-1].payload["reflection"] == "I’ve been careful."
