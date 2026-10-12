from __future__ import annotations

import json
from pathlib import Path

from sentientos.forge_index import rebuild_index


def test_index_does_not_assign_latest_unrelated_trace_pack_to_active_quarantine(
    tmp_path: Path,
) -> None:
    quarantine = tmp_path / "glow/forge/quarantine.json"
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    quarantine.write_text(json.dumps({
        "schema_version": 1,
        "active": True,
        "activated_at": "2026-01-01T00:00:00Z",
        "activated_by": "auto",
        "last_incident_id": "active-incident",
        "freeze_forge": True,
        "allow_automerge": False,
        "allow_publish": False,
        "allow_federation_sync": True,
        "notes": [],
    }, sort_keys=True) + "\n", encoding="utf-8")
    pulse = tmp_path / "pulse"
    pulse.mkdir(parents=True, exist_ok=True)
    (pulse / "governance_traces.jsonl").write_text(json.dumps({
        "trace_id": "unrelated-trace", "final_decision": "hold",
    }, sort_keys=True) + "\n", encoding="utf-8")
    (pulse / "remediation_packs.jsonl").write_text(json.dumps({
        "pack_id": "unrelated-pack", "incident_id": "different-incident",
        "governance_trace_id": "unrelated-trace", "status": "queued",
    }, sort_keys=True) + "\n", encoding="utf-8")
    runs = tmp_path / "glow/forge/remediation/runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "run_unrelated.json").write_text(json.dumps({
        "run_id": "unrelated-run", "pack_id": "unrelated-pack", "status": "completed",
    }, sort_keys=True) + "\n", encoding="utf-8")

    index = rebuild_index(tmp_path)

    assert index["last_trace_remediation_pack_id"] == "unrelated-pack"
    assert index["last_quarantine_remediation_pack_id"] is None
    assert index["last_quarantine_remediation_status"] == "missing"


def test_index_reports_invalid_quarantine_as_unknown_and_restrictive(tmp_path: Path) -> None:
    target = tmp_path / "glow/forge/quarantine.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{truncated", encoding="utf-8")

    index = rebuild_index(tmp_path)

    assert index["quarantine_active"] is None
    assert index["quarantine_custody_status"] == "invalid:quarantine_json_invalid"
    assert index["quarantine_incident_custody"] == {
        "status": "custody_invalid",
        "reason": "quarantine_json_invalid",
        "attack_established": False,
        "defensive_consequence_established": False,
    }
    assert index["mode_effective_toggles"]["allow_forge_mutation"] is False
    assert index["mode_effective_toggles"]["allow_publish"] is False
    assert index["mode_effective_toggles"]["allow_automerge"] is False
