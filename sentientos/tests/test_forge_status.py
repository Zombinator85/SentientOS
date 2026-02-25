from __future__ import annotations

import json
import os
from pathlib import Path

from scripts import forge_status
from sentientos.attestation import append_jsonl, write_json


def _seed_integrity(root: Path) -> None:
    payload = {
        "schema_version": 1,
        "ts": "2099-01-01T00:00:00Z",
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
    write_json(root / "glow/forge/integrity/status_2099-01-01T00-00-00Z.json", payload)


def _seed_snapshot(root: Path) -> None:
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
    write_json(root / "glow/forge/attestation/snapshots/snapshot_2099-01-01T00-00-00Z.json", payload)
    append_jsonl(root / "pulse/attestation_snapshots.jsonl", payload | {"path": "glow/forge/attestation/snapshots/snapshot_2099-01-01T00-00-00Z.json"})


def test_forge_status_json_is_deterministic(tmp_path: Path, capsys) -> None:
    _seed_integrity(tmp_path)
    _seed_snapshot(tmp_path)

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
    assert out1 == out2
    assert json.loads(out1)["snapshot"]["signature_tip"]["sig_hash"] == "abc123"


def test_forge_status_exit_codes(tmp_path: Path) -> None:
    old = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert forge_status.main(["--json"]) == 3

        _seed_integrity(tmp_path)
        status_path = tmp_path / "glow/forge/integrity/status_2099-01-01T00-00-00Z.json"
        payload = json.loads(status_path.read_text(encoding="utf-8"))
        payload["mutation_allowed"] = False
        payload["primary_reason"] = "doctrine_identity_mismatch"
        write_json(status_path, payload)
        assert forge_status.main(["--json"]) == 2

        payload["mutation_allowed"] = True
        payload["gate_results"][0]["status"] = "warn"
        payload["gate_results"][0]["reason"] = "warned"
        write_json(status_path, payload)
        assert forge_status.main(["--json"]) == 1
    finally:
        os.chdir(old)
