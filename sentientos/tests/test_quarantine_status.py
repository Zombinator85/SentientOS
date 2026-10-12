from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from scripts import quarantine_status
from sentientos.integrity_incident import build_incident, write_incident


def _state(root: Path, incident_id: str | None, activated_at: str | None) -> None:
    path = root / "glow/forge/quarantine.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "active": True,
        "activated_at": activated_at,
        "activated_by": "auto",
        "last_incident_id": incident_id,
        "freeze_forge": True,
        "allow_automerge": False,
        "allow_publish": False,
        "allow_federation_sync": False,
        "notes": [],
    }, sort_keys=True) + "\n", encoding="utf-8")


def test_status_reports_bounded_custody_without_printing_incident_narrative(
    tmp_path: Path, monkeypatch, capsys,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    at = "2026-01-01T00:00:00Z"
    incident = build_incident(
        triggers=["fixture-trigger"], enforcement_mode="enforce", severity="warning",
        context={"attacker_text": "RAW_ATTACKER_NARRATIVE"},
        suggested_actions=["RAW_SUGGESTED_COMMAND"], created_at=at,
        governance_trace_id="fixture-trace",
    )
    write_incident(tmp_path, incident, quarantine_activated=True)
    _state(tmp_path, incident.incident_id, at)

    assert quarantine_status.main() == 0
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert payload["quarantine_active"] is True
    assert payload["incident_custody"]["status"] == "complete_local_custody"
    assert payload["incident_custody"]["feed_is_authenticated"] is False
    assert "RAW_ATTACKER_NARRATIVE" not in output
    assert "RAW_SUGGESTED_COMMAND" not in output
    assert "suggested_actions" not in output


def test_status_keeps_malformed_quarantine_unknown(tmp_path: Path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "glow/forge/quarantine.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{truncated", encoding="utf-8")

    assert quarantine_status.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["quarantine"] is None
    assert payload["quarantine_active"] is None
    assert payload["quarantine_custody_status"] == "invalid:quarantine_json_invalid"
    assert payload["incident_custody"]["status"] == "not_checked"


def test_status_does_not_follow_substituted_incident_directory(
    tmp_path: Path, monkeypatch, capsys,
) -> None:  # type: ignore[no-untyped-def]
    if os.name != "posix":
        pytest.skip("descriptor-relative symlink custody case is POSIX-only")
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    at = "2026-01-01T00:00:00Z"
    incident = build_incident(
        triggers=["fixture-trigger"], enforcement_mode="enforce", severity="warning",
        context={"attacker_text": "SYMLINK_TARGET_NARRATIVE"},
        suggested_actions=["SYMLINK_TARGET_COMMAND"], created_at=at,
    )
    write_incident(outside, incident, quarantine_activated=True)
    incident_dir = root / "glow/forge/incidents"
    incident_dir.parent.mkdir(parents=True, exist_ok=True)
    incident_dir.symlink_to(outside / "glow/forge/incidents", target_is_directory=True)
    _state(root, incident.incident_id, at)
    monkeypatch.chdir(root)

    assert quarantine_status.main() == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["incident_custody"]["artifact_status"] == "invalid"
    assert "SYMLINK_TARGET_NARRATIVE" not in output
    assert "SYMLINK_TARGET_COMMAND" not in output
