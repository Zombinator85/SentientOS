from __future__ import annotations

import json
from pathlib import Path

from scripts import run_remediation_pack
from sentientos.artifact_catalog import append_catalog_entry
from sentientos.forge_index import rebuild_index


def _pack(root: Path) -> Path:
    path = root / "glow/forge/remediation/packs/pack_pack-index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "pack_id": "pack-index",
        "incident_id": "incident-index",
        "governance_trace_id": "trace-index",
        "status": "proposed",
        "steps": [{"name": "verify", "command": "python scripts/verify_doctrine_identity.py",
            "allowlisted": True, "destructive": False}],
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    append_catalog_entry(root, kind="remediation_pack", artifact_id="pack-index",
        relative_path="glow/forge/remediation/packs/pack_pack-index.json",
        schema_name="remediation_pack", schema_version=1,
        links={"pack_id": "pack-index", "incident_id": "incident-index", "trace_id": "trace-index"},
        summary={"status": "proposed"})
    return path


def _untrusted_completed_catalog_claim(root: Path) -> None:
    append_catalog_entry(root, kind="remediation_run", artifact_id="run_20260101T000000Z_pack-index",
        relative_path="glow/forge/remediation/runs/run_20260101T000000Z_pack-index.json",
        schema_name="remediation_run", schema_version=1,
        links={"run_id": "run_20260101T000000Z_pack-index", "pack_id": "pack-index"},
        summary={"status": "completed"})


def test_forge_index_does_not_project_catalog_success_without_owner_report(tmp_path: Path) -> None:
    _pack(tmp_path)
    _untrusted_completed_catalog_claim(tmp_path)

    index = rebuild_index(tmp_path)
    summary = json.loads(index["last_remediation_run_summary"])

    assert summary["status"] == "invalid"
    assert summary["custody_status"] == "invalid:catalog_run_without_verified_owner_report"


def test_forge_index_surfaces_interrupted_intent_instead_of_missing_or_success(
        tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pack_path = _pack(tmp_path)
    run_remediation_pack._publish_run_intent(
        tmp_path,
        payload=json.loads(pack_path.read_text(encoding="utf-8")),
        pack_bytes=pack_path.read_bytes(),
        pack_relative_path="glow/forge/remediation/packs/pack_pack-index.json",
        run_id="run_20260101T000000Z_pack-index",
        stamp="20260101T000000Z",
    )
    _untrusted_completed_catalog_claim(tmp_path)

    index = rebuild_index(tmp_path)
    summary = json.loads(index["last_remediation_run_summary"])

    assert summary["status"] == "invalid"
    assert summary["custody_status"] == "invalid:run_interrupted_without_final_report"


def test_forge_index_projects_owner_reconciled_run_and_intent(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pack_path = _pack(tmp_path)
    monkeypatch.setattr(run_remediation_pack, "_run_allowed", lambda _command, *, root: (True, 0, ""))
    report = run_remediation_pack.execute_pack_file(pack_path, root=tmp_path)
    attempts = tmp_path / "pulse/auto_remediation_attempts.jsonl"
    attempts.parent.mkdir(parents=True, exist_ok=True)
    attempts.write_text(json.dumps({
        "attempted_at": report["generated_at"],
        "pack_id": "pack-index",
        "run_id": report["run_id"],
        "status": "completed",
    }) + "\n", encoding="utf-8")

    index = rebuild_index(tmp_path)
    summary = json.loads(index["last_remediation_run_summary"])

    assert summary["run_id"] == report["run_id"]
    assert summary["status"] == "completed"
    assert summary["custody_status"] == "locally_reconciled"
    assert index["auto_remediation_status"] == "succeeded"
