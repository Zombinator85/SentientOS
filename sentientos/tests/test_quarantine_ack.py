from __future__ import annotations

import json
from pathlib import Path

from scripts import quarantine_ack


def test_ack_reports_invalid_custody_without_overwriting_bytes(
    tmp_path: Path, monkeypatch, capsys,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "glow/forge/quarantine.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    damaged = b"{broken protective state"
    target.write_bytes(damaged)

    assert quarantine_ack.main(["--note", "operator acknowledgment"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "blocked"
    assert payload["failure"] == "quarantine_custody_invalid"
    assert payload["quarantine_active"] is None
    assert payload["quarantine_custody_status"] == "invalid:quarantine_json_invalid"
    assert target.read_bytes() == damaged
    assert not (tmp_path / "pulse/forge_events.jsonl").exists()


def test_ack_can_initialize_genuine_first_use_state(
    tmp_path: Path, monkeypatch, capsys,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sentientos.event_stream.FORGE_EVENTS_PATH",
        tmp_path / "pulse" / "forge_events.jsonl")

    assert quarantine_ack.main(["--note", "first-use acknowledgment"]) == 0
    payload = json.loads(capsys.readouterr().out)
    state = json.loads((tmp_path / "glow/forge/quarantine.json").read_text(encoding="utf-8"))

    assert payload["status"] == "ok"
    assert state["active"] is False
    assert state["acknowledged_at"] is not None
    assert any(note.endswith(":first-use acknowledgment") for note in state["notes"])
    assert (tmp_path / "pulse/forge_events.jsonl").exists()
