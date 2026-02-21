from __future__ import annotations

import json
from pathlib import Path

from scripts import quarantine_clear


def _setup_quarantine(tmp_path: Path) -> None:
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/quarantine.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "active": True,
                "activated_at": "2026-01-01T00:00:00Z",
                "activated_by": "auto",
                "last_incident_id": "inc-1",
                "freeze_forge": True,
                "allow_automerge": False,
                "allow_publish": False,
                "allow_federation_sync": True,
                "notes": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _setup_pack(tmp_path: Path) -> Path:
    pack_path = tmp_path / "glow/forge/remediation/packs/pack_pack-1.json"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(
        json.dumps({"pack_id": "pack-1", "incident_id": "inc-1", "schema_version": 1, "steps": []}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pulse = tmp_path / "pulse/remediation_packs.jsonl"
    pulse.parent.mkdir(parents=True, exist_ok=True)
    pulse.write_text(
        json.dumps(
            {
                "pack_id": "pack-1",
                "incident_id": "inc-1",
                "governance_trace_id": "trace-1",
                "pack_path": "glow/forge/remediation/packs/pack_pack-1.json",
                "status": "queued",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return pack_path


def _monkeypatch_integrity_ok(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("scripts.quarantine_clear.verify_receipt_chain", lambda root: type("R", (), {"ok": True, "to_dict": lambda self: {"status": "ok"}})())
    monkeypatch.setattr("scripts.quarantine_clear.verify_receipt_anchors", lambda root: type("A", (), {"ok": True, "to_dict": lambda self: {"status": "ok"}})())
    monkeypatch.setattr("scripts.quarantine_clear.verify_doctrine_identity", lambda root: (True, {"ok": True}))
    monkeypatch.setattr("scripts.quarantine_clear.federation_integrity_gate", lambda root, context: {"blocked": False, "status": "ok"})


def test_quarantine_clear_requires_remediation_run(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    _setup_quarantine(tmp_path)
    _setup_pack(tmp_path)
    _monkeypatch_integrity_ok(monkeypatch)
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_REQUIRE_REMEDIATION", "1")

    assert quarantine_clear.main([]) == 1


def test_quarantine_clear_succeeds_with_completed_run(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    _setup_quarantine(tmp_path)
    _setup_pack(tmp_path)
    _monkeypatch_integrity_ok(monkeypatch)
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_REQUIRE_REMEDIATION", "1")

    run_path = tmp_path / "glow/forge/remediation/runs/run_20260101T000000Z_pack-1.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(json.dumps({"run_id": "run_1", "pack_id": "pack-1", "status": "completed"}, sort_keys=True) + "\n", encoding="utf-8")

    assert quarantine_clear.main(["--note", "remediated"]) == 0


def test_quarantine_clear_override_records_docket(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    _setup_quarantine(tmp_path)
    _setup_pack(tmp_path)
    _monkeypatch_integrity_ok(monkeypatch)
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_REQUIRE_REMEDIATION", "1")
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_REMEDIATION_OVERRIDE", "1")

    assert quarantine_clear.main(["--note", "break-glass"]) == 0
    dockets = sorted((tmp_path / "glow/forge/incidents").glob("incident_*.json"))
    assert dockets
    payload = json.loads(dockets[-1].read_text(encoding="utf-8"))
    assert payload["context"]["override_note"]


def test_incident_pack_linkage_deterministic(tmp_path: Path) -> None:
    from sentientos.integrity_incident import build_incident, write_incident
    from sentientos.remediation_pack import find_pack_for_incident_or_trace

    _setup_pack(tmp_path)
    incident = build_incident(
        triggers=["audit_chain_broken"],
        enforcement_mode="enforce",
        severity="enforced",
        context={"k": "v"},
        evidence_paths=[],
        suggested_actions=[],
        created_at="2026-01-01T00:00:00Z",
        governance_trace_id="trace-1",
        remediation_pack_id="pack-1",
    )
    write_incident(tmp_path, incident)
    linked = find_pack_for_incident_or_trace(tmp_path, incident_id=incident.incident_id, governance_trace_id="trace-1")
    assert linked is not None
    assert linked["pack_id"] == "pack-1"
