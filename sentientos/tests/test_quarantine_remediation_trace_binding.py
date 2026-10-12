from __future__ import annotations

import json
from pathlib import Path

from scripts import quarantine_clear
from sentientos.integrity_incident import build_incident, write_incident


def _active_quarantine(root: Path, *, incident_id: str = "active-incident") -> None:
    target = root / "glow/forge/quarantine.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "schema_version": 1,
        "active": True,
        "activated_at": "2026-01-01T00:00:00Z",
        "activated_by": "auto",
        "last_incident_id": incident_id,
        "freeze_forge": True,
        "allow_automerge": False,
        "allow_publish": False,
        "allow_federation_sync": True,
        "notes": [],
    }, sort_keys=True) + "\n", encoding="utf-8")


def _unrelated_completed_remediation(root: Path) -> None:
    pack_id = "unrelated-pack"
    trace_id = "unrelated-trace"
    pack_path = root / f"glow/forge/remediation/packs/pack_{pack_id}.json"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(json.dumps({
        "pack_id": pack_id, "incident_id": "different-incident",
        "schema_version": 1, "steps": [],
    }) + "\n", encoding="utf-8")
    pulse = root / "pulse"
    pulse.mkdir(parents=True, exist_ok=True)
    (pulse / "remediation_packs.jsonl").write_text(json.dumps({
        "pack_id": pack_id, "incident_id": "different-incident",
        "governance_trace_id": trace_id,
        "pack_path": str(pack_path.relative_to(root)), "status": "queued",
    }, sort_keys=True) + "\n", encoding="utf-8")
    (pulse / "governance_traces.jsonl").write_text(json.dumps({
        "trace_id": trace_id, "final_decision": "hold",
    }, sort_keys=True) + "\n", encoding="utf-8")
    run_path = root / f"glow/forge/remediation/runs/run_completed_{pack_id}.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(json.dumps({
        "run_id": "unrelated-run", "pack_id": pack_id, "status": "completed",
    }) + "\n", encoding="utf-8")


def test_real_clear_entrypoint_rejects_remediation_for_unrelated_trace(
    monkeypatch, tmp_path: Path, capsys,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    _active_quarantine(tmp_path)
    _unrelated_completed_remediation(tmp_path)
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_REQUIRE_REMEDIATION", "1")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust/state.json"))
    from sentientos.runtime_governor import reset_runtime_governor
    reset_runtime_governor()

    result = quarantine_clear.main([])
    report = json.loads(capsys.readouterr().out)
    state = json.loads((tmp_path / "glow/forge/quarantine.json").read_text(encoding="utf-8"))

    assert result == 1
    assert "remediation_incomplete" in report["failures"]
    assert report["checks"]["quarantine_remediation"]["governance_trace_id"] is None
    assert state["active"] is True
    reset_runtime_governor()


def test_trace_fallback_comes_from_exact_canonical_incident_artifact(tmp_path: Path) -> None:
    activated_at = "2026-01-01T00:00:00Z"
    incident = build_incident(
        triggers=["fixture-trigger"], enforcement_mode="enforce", severity="warning",
        created_at=activated_at, governance_trace_id="incident-trace",
    )
    write_incident(tmp_path, incident, quarantine_activated=True)

    assert quarantine_clear._quarantine_trace_id_from_incident(
        tmp_path, incident_id=incident.incident_id, activated_at=activated_at,
    ) == "incident-trace"
    assert quarantine_clear._quarantine_trace_id_from_incident(
        tmp_path, incident_id="different-incident", activated_at=activated_at,
    ) is None


def test_clear_reports_invalid_custody_without_replacing_damaged_bytes(
    monkeypatch, tmp_path: Path, capsys,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "glow/forge/quarantine.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    damaged = b"{truncated protective record"
    path.write_bytes(damaged)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime-state"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust/state.json"))
    from sentientos.runtime_governor import reset_runtime_governor
    reset_runtime_governor()

    assert quarantine_clear.main([]) == 1
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["status"] == "blocked"
    assert report["failures"] == ["quarantine_custody_invalid"]
    assert report["checks"]["quarantine"]["active"] is None
    assert report["checks"]["quarantine"]["custody_status"] == "invalid:quarantine_json_invalid"
    assert path.read_bytes() == damaged
    assert '"active": false' not in output.lower()
    reset_runtime_governor()
