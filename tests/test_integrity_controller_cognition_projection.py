from __future__ import annotations

import json
from pathlib import Path

from sentientosd import _integrity_controller_world_state_record


def test_compounded_custody_failures_reach_world_state_without_invented_pressure(
    tmp_path: Path, monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_INTEGRITY_CONTROLLER_OBSERVATION", "1")
    quarantine = tmp_path / "glow/forge/quarantine.json"
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    quarantine.write_text("{malformed protective state", encoding="utf-8")
    feed = tmp_path / "pulse/integrity_incidents.jsonl"
    feed.parent.mkdir(parents=True, exist_ok=True)
    feed.write_text("{malformed pressure input", encoding="utf-8")

    record = _integrity_controller_world_state_record(
        tmp_path, observed_at="2026-10-12T00:00:00+00:00",
    )

    assert record is not None
    payload = record["payload"]
    assert payload["controller_posture"] == "fail"
    assert payload["failed_gate_count"] >= 2
    gates = {gate["name"]: gate for gate in payload["gate_results"]}
    assert gates["quarantine_custody"]["status"] == "fail"
    assert gates["integrity_pressure_input"]["status"] == "fail"
    assert gates["quarantine_custody"]["reason"] == (
        "quarantine_custody_invalid:quarantine_json_invalid"
    )
    assert gates["integrity_pressure_input"]["reason"].startswith(
        "integrity_pressure_input_invalid:"
    )
    assert payload["integrity_status_digest"] is not None
    assert payload["attack_established"] is False
    assert payload["compromise_established"] is False
    assert payload["effect_proven"] is False
    assert payload["authority"] is False
    assert "pressure_summary" not in payload
    assert "mutation_allowed" not in payload
