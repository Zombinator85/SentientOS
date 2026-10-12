from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from scripts import quarantine_clear, run_remediation_pack
from sentientos.integrity_incident import build_incident, write_incident
from sentientos.receipt_chain import append_receipt
from sentientos.auto_remediation import should_auto_run_pack
from sentientos.remediation_pack import remediation_status_for_pack


def _pack(root: Path, *, incident_id: str = "incident-1", pack_id: str = "pack-1") -> Path:
    path = root / f"glow/forge/remediation/packs/pack_{pack_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "pack_id": pack_id,
        "incident_id": incident_id,
        "status": "proposed",
        "steps": [{"name": "verify", "command": "python scripts/verify_doctrine_identity.py",
            "allowlisted": True, "destructive": False}],
    }, sort_keys=True) + "\n", encoding="utf-8")
    pulse = root / "pulse/remediation_packs.jsonl"
    pulse.parent.mkdir(parents=True, exist_ok=True)
    pulse.write_text(json.dumps({
        "pack_id": pack_id,
        "incident_id": incident_id,
        "governance_trace_id": "trace-1",
        "pack_path": path.relative_to(root).as_posix(),
        "status": "queued",
    }, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _active_state(root: Path, *, incident_id: str, activated_at: str) -> None:
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
        "allow_federation_sync": True,
        "notes": [],
    }, sort_keys=True) + "\n", encoding="utf-8")


def _isolate_control_plane(monkeypatch, root: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(root / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(root / "runtime-state"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(root / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(root))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(root / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(root / "trust/state.json"))
    from sentientos.runtime_governor import reset_runtime_governor
    reset_runtime_governor()


def test_bare_completed_file_is_not_a_remediation_run(tmp_path: Path) -> None:
    pack_path = _pack(tmp_path)
    run_path = tmp_path / "glow/forge/remediation/runs/run_20260101T000000Z_pack-1.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(json.dumps({"run_id": "run_20260101T000000Z_pack-1", "pack_id": "pack-1", "status": "completed"}) + "\n")

    status, report = remediation_status_for_pack(tmp_path, pack_id="pack-1")

    assert status == "invalid"
    assert report is not None
    assert report["custody_status"] == "invalid:run_identity_mismatch"

    decision = should_auto_run_pack(tmp_path, operating_mode="recovery",
        pack={"pack_id": "pack-1", "pack_path": pack_path.relative_to(tmp_path).as_posix()},
        incident_id="incident-1", governance_trace_id="trace-1")
    assert decision.status == "failed"
    assert decision.reason == "prior_run_custody_invalid"


def test_duplicate_keys_and_report_symlinks_fail_closed(tmp_path: Path) -> None:
    _pack(tmp_path)
    run_dir = tmp_path / "glow/forge/remediation/runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "run_20260101T000000Z_pack-1.json"
    target.write_text('{"run_id":"first","run_id":"second","pack_id":"pack-1","status":"completed"}\n')
    status, report = remediation_status_for_pack(tmp_path, pack_id="pack-1")
    assert status == "invalid"
    assert report is not None and report["custody_status"] == "invalid:duplicate_json_key"

    target.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n")
    target.symlink_to(outside)
    status, report = remediation_status_for_pack(tmp_path, pack_id="pack-1")
    assert status == "invalid"
    assert report is not None and str(report["custody_status"]).startswith("invalid:")


def test_runner_publishes_reconciled_bounded_report(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pack_path = _pack(tmp_path)
    monkeypatch.setattr(run_remediation_pack, "_run_allowed", lambda _command, *, root: (True, 0, ""))

    report = run_remediation_pack.execute_pack_file(pack_path, root=tmp_path)
    status, recovered = remediation_status_for_pack(tmp_path, pack_id="pack-1")

    assert status == "completed"
    assert recovered is not None
    assert recovered["run_id"] == report["run_id"]
    assert recovered["pack_sha256"] == report["pack_sha256"]
    assert recovered["intent_id"] == report["intent_id"]
    intent_path = tmp_path / "glow/forge/remediation/intents" / f"{report['intent_id']}.json"
    assert hashlib.sha256(intent_path.read_bytes()).hexdigest() == report["intent_sha256"]
    assert recovered["custody_status"] == "locally_reconciled"
    assert recovered["execution_authenticity"] == "owner_report_not_independently_authenticated"
    path = tmp_path / str(report["report_path"])
    assert path.stat().st_mode & 0o077 == 0


def test_report_publication_interruption_persists_intent_and_blocks_replay(
        tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pack_path = _pack(tmp_path)
    command_calls = 0
    publication_calls = 0
    original_publish = run_remediation_pack.publish_immutable_bytes

    def execute_once(_command: str, *, root: Path) -> tuple[bool, int, str]:
        nonlocal command_calls
        command_calls += 1
        return True, 0, ""

    def interrupt_report(path: Path, data: bytes, *, max_bytes: int,
            collision_code: str) -> str:
        nonlocal publication_calls
        publication_calls += 1
        if publication_calls == 2:
            raise RuntimeError("simulated interruption after command and durable intent")
        return original_publish(path, data, max_bytes=max_bytes, collision_code=collision_code)

    monkeypatch.setattr(run_remediation_pack, "_run_allowed", execute_once)
    monkeypatch.setattr(run_remediation_pack, "publish_immutable_bytes", interrupt_report)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_remediation_pack.execute_pack_file(pack_path, root=tmp_path)

    status, recovered = remediation_status_for_pack(tmp_path, pack_id="pack-1")
    assert status == "invalid"
    assert recovered is not None
    assert recovered["custody_status"] == "invalid:run_interrupted_without_final_report"
    decision = should_auto_run_pack(tmp_path, operating_mode="recovery",
        pack={"pack_id": "pack-1", "pack_path": pack_path.relative_to(tmp_path).as_posix()},
        incident_id="incident-1", governance_trace_id="trace-1")
    assert decision.status == "failed"
    assert decision.reason == "prior_run_custody_invalid"
    with pytest.raises(ValueError, match="prior_run_custody_invalid"):
        run_remediation_pack.execute_pack_file(pack_path, root=tmp_path)
    assert command_calls == 1


def test_newer_conflicting_report_shadows_older_success(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pack_path = _pack(tmp_path)
    monkeypatch.setattr(run_remediation_pack, "_run_allowed", lambda _command, *, root: (True, 0, ""))
    first = run_remediation_pack.execute_pack_file(pack_path, root=tmp_path)
    run_dir = tmp_path / "glow/forge/remediation/runs"
    later_path = run_dir / "run_20261231T235959Z_pack-1.json"
    later_path.write_text(json.dumps({
        "schema_version": 1,
        "run_id": later_path.stem,
        "pack_id": "pack-1",
        "pack_path": "glow/forge/remediation/packs/pack_pack-1.json",
        "incident_id": "incident-1",
        "generated_at": "2026-12-31T23:59:59Z",
        "status": "completed",
        "steps": [],
    }, sort_keys=True) + "\n")

    status, recovered = remediation_status_for_pack(tmp_path, pack_id="pack-1")

    assert first["status"] == "completed"
    assert status == "invalid"
    assert recovered is not None
    assert recovered["custody_status"] == "invalid:run_report_conflicts_with_latest_intent"


def test_real_clear_blocks_bare_remediation_claim(monkeypatch, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    incident_time = "2026-01-01T00:00:00Z"
    incident = build_incident(triggers=["fixture"], enforcement_mode="enforce", severity="warning",
        created_at=incident_time, governance_trace_id="trace-1")
    write_incident(tmp_path, incident, quarantine_activated=True)
    _active_state(tmp_path, incident_id=incident.incident_id, activated_at=incident_time)
    _pack(tmp_path, incident_id=incident.incident_id)
    _isolate_control_plane(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_REQUIRE_REMEDIATION", "1")
    run_path = tmp_path / "glow/forge/remediation/runs/run_20260101T000000Z_pack-1.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(json.dumps({"run_id": run_path.stem, "pack_id": "pack-1", "status": "completed"}) + "\n")

    assert quarantine_clear.main([]) == 1
    output = json.loads(capsys.readouterr().out)
    assert "remediation_incomplete" in output["failures"]
    assert output["checks"]["quarantine_remediation"]["status"] == "invalid"
    assert json.loads((tmp_path / "glow/forge/quarantine.json").read_text())["active"] is True
    from sentientos.runtime_governor import reset_runtime_governor
    reset_runtime_governor()


def test_real_clear_accepts_runner_report_with_exact_step_lineage(
    monkeypatch, tmp_path: Path, capsys,
) -> None:  # type: ignore[no-untyped-def]
    incident_time = "2026-01-01T00:00:00Z"
    incident = build_incident(triggers=["fixture"], enforcement_mode="enforce", severity="warning",
        created_at=incident_time, governance_trace_id="trace-1")
    write_incident(tmp_path, incident, quarantine_activated=True)
    _active_state(tmp_path, incident_id=incident.incident_id, activated_at=incident_time)
    pack_path = _pack(tmp_path, incident_id=incident.incident_id)
    append_receipt(tmp_path, {"schema_version": 1, "receipt_id": "fixture-receipt",
        "created_at": incident_time, "status": "fixture"})
    _isolate_control_plane(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_REQUIRE_REMEDIATION", "1")
    # Only the final command boundary is replaced; quarantine, custody,
    # integrity, governance, and clear admission remain real.
    monkeypatch.setattr(run_remediation_pack, "_run_allowed", lambda _command, *, root: (True, 0, ""))
    runner_report = run_remediation_pack.execute_pack_file(pack_path, root=tmp_path)

    assert quarantine_clear.main(["--note", "verified local run fixture"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checks"]["quarantine_remediation"]["status"] == "completed"
    assert report["checks"]["quarantine_remediation"]["remediation_run_id"] == runner_report["run_id"]
    assert json.loads((tmp_path / "glow/forge/quarantine.json").read_text())["active"] is False
    from sentientos.runtime_governor import reset_runtime_governor
    reset_runtime_governor()
