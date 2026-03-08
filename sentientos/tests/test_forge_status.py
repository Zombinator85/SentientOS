from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import forge_status
from sentientos import artifact_catalog
from sentientos.attestation import append_jsonl, write_json


def _seed_integrity(root: Path) -> dict[str, object]:
    payload = {
        "schema_version": 1,
        "ts": "2099-01-01T00:00:00Z",
        "status": "ok",
        "strategic_posture": "balanced",
        "operating_mode": "normal",
        "pressure_summary": {"level": "low", "metrics": {}},
        "quarantine_active": False,
        "risk_budget_summary": {},
        "mutation_allowed": True,
        "publish_allowed": True,
        "automerge_allowed": True,
        "gate_results": [
            {"name": "strategic_signatures", "status": "ok", "reason": "ok", "evidence_paths": [], "checked_at": "2099-01-01T00:00:00Z"},
            {"name": "rollup_signatures", "status": "ok", "reason": "ok", "evidence_paths": [], "checked_at": "2099-01-01T00:00:00Z"},
            {"name": "attestation_snapshot_signatures", "status": "ok", "reason": "ok", "evidence_paths": [], "checked_at": "2099-01-01T00:00:00Z"},
        ],
        "primary_reason": "integrity_ok",
        "reason_stack": [],
        "recommended_actions": [],
        "policy_hash": "policy-hash",
        "budget_exhausted": False,
        "budget_remaining": {"verify_streams": 1},
    }
    return payload


def _seed_snapshot(root: Path) -> dict[str, object]:
    payload = {
        "schema_version": 1,
        "ts": "2099-01-01T00:00:00Z",
        "policy_hash": "policy-hash",
        "integrity_status_hash": "status-hash",
        "latest_rollup_sig_hash": None,
        "latest_strategic_sig_hash": None,
        "latest_goal_graph_hash": None,
        "latest_catalog_checkpoint_hash": None,
        "doctrine_bundle_sha256": None,
        "witness_summary": {},
    }
    return payload


def test_forge_status_json_is_deterministic(tmp_path: Path, capsys) -> None:
    integrity_payload = _seed_integrity(tmp_path)
    snapshot_payload = _seed_snapshot(tmp_path)
    write_json(tmp_path / "glow/forge/integrity/status_2099-01-01T00-00-00Z.json", integrity_payload)
    write_json(tmp_path / "glow/forge/attestation/snapshots/snapshot_2099-01-01T00-00-00Z.json", snapshot_payload)
    append_jsonl(tmp_path / "pulse/attestation_snapshots.jsonl", snapshot_payload | {"path": "glow/forge/attestation/snapshots/snapshot_2099-01-01T00-00-00Z.json"})

    (tmp_path / "glow/forge/attestation/signatures/attestation_snapshots").mkdir(parents=True, exist_ok=True)
    append_jsonl(
        tmp_path / "glow/forge/attestation/signatures/attestation_snapshots/signatures_index.jsonl",
        {"sig_hash": "abc123", "created_at": "2099-01-01T00:00:00Z"},
    )

    old = Path.cwd()
    try:
        os.chdir(tmp_path)
        rc1 = forge_status.main(["--json"])
        out1 = capsys.readouterr().out
        rc2 = forge_status.main(["--json"])
        out2 = capsys.readouterr().out
    finally:
        os.chdir(old)

    assert rc1 == 0
    assert rc2 == 0
    payload = json.loads(out1)
    payload_again = json.loads(out2)
    for item in (payload, payload_again):
        provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        for key in ("integrity_status", "attestation_snapshot"):
            section = provenance.get(key)
            if isinstance(section, dict):
                section.pop("resolution_source", None)
    assert payload == payload_again
    assert payload["snapshot"]["signature_tip"]["sig_hash"] == "abc123"
    assert payload["governor"]["operating_mode"] == "normal"


def test_forge_status_exit_codes(tmp_path: Path) -> None:
    old = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert forge_status.main(["--json"]) == 3

        payload = _seed_integrity(tmp_path)
        payload["mutation_allowed"] = False
        payload["primary_reason"] = "doctrine_identity_mismatch"
        write_json(tmp_path / "glow/forge/integrity/status_2099-01-01T00-00-00Z.json", payload)
        assert forge_status.main(["--json"]) == 2

        payload["mutation_allowed"] = True
        payload["status"] = "warn"
        write_json(tmp_path / "glow/forge/integrity/status_2099-01-01T00-00-00Z.json", payload)
        assert forge_status.main(["--json"]) == 1
    finally:
        os.chdir(old)


def test_forge_status_catalog_resolution_is_first_class(tmp_path: Path, capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    integrity_payload = _seed_integrity(tmp_path)
    status_rel = "glow/forge/integrity/status_2099-01-01T00-00-00Z.json"
    write_json(tmp_path / status_rel, integrity_payload)
    artifact_catalog.append_catalog_entry(
        tmp_path,
        kind="integrity_status",
        artifact_id="2099-01-01T00:00:00Z",
        relative_path=status_rel,
        schema_name="integrity_status",
        schema_version=1,
        links={"policy_hash": "policy-hash"},
        summary={"status": "ok"},
        ts="2099-01-01T00:00:00Z",
    )
    monkeypatch.chdir(tmp_path)

    forge_status.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["provenance"]["integrity_status"]["resolution_source"] == "catalog"


def test_forge_status_includes_constitution_summary(tmp_path: Path, capsys) -> None:
    integrity_payload = _seed_integrity(tmp_path)
    write_json(tmp_path / "glow/forge/integrity/status_2099-01-01T00-00-00Z.json", integrity_payload)
    write_json(
        tmp_path / "glow/constitution/constitution_summary.json",
        {
            "constitution_state": "healthy",
            "constitutional_digest": "digest-const",
            "effective_posture": "nominal",
        },
    )

    old = Path.cwd()
    try:
        os.chdir(tmp_path)
        forge_status.main(["--json"])
        payload = json.loads(capsys.readouterr().out)
    finally:
        os.chdir(old)

    assert payload["constitution"]["state"] == "healthy"
    assert payload["constitution"]["digest"] == "digest-const"
    assert payload["provenance"]["constitution_summary"]["path"] == "glow/constitution/constitution_summary.json"


def test_forge_status_surfaces_constitution_restoration_hints(tmp_path: Path, capsys) -> None:
    integrity_payload = _seed_integrity(tmp_path)
    write_json(tmp_path / "glow/forge/integrity/status_2099-01-01T00-00-00Z.json", integrity_payload)
    write_json(
        tmp_path / "glow/constitution/constitution_summary.json",
        {
            "constitution_state": "missing",
            "constitutional_digest": "digest-const",
            "effective_posture": "unknown",
            "missing_required_artifacts": ["audit_trust_state"],
            "restoration_hints": ["audit_trust_state missing: run python -m sentientos.start"],
        },
    )

    old = Path.cwd()
    try:
        os.chdir(tmp_path)
        forge_status.main(["--json"])
        payload = json.loads(capsys.readouterr().out)
    finally:
        os.chdir(old)

    assert payload["constitution"]["missing_required_artifacts"] == ["audit_trust_state"]
    assert payload["constitution"]["restoration_hints"]
    assert payload["health_domain"]["runtime_data"] in {"healthy", "degraded"}



def test_forge_status_script_runs_without_pythonpath(tmp_path: Path) -> None:
    payload = _seed_integrity(tmp_path)
    write_json(tmp_path / "glow/forge/integrity/status_2099-01-01T00-00-00Z.json", payload)
    script = Path(__file__).resolve().parents[2] / "scripts" / "forge_status.py"
    completed = subprocess.run([sys.executable, str(script), "--json"], cwd=tmp_path, check=False, capture_output=True, text=True)
    assert completed.returncode == 0
    assert '"integrity_overall":"ok"' in completed.stdout

