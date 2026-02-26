from __future__ import annotations

import json
from pathlib import Path

from scripts import forge_replay, forge_status
from sentientos import artifact_catalog
from sentientos.attestation import append_jsonl, write_json
from sentientos.operator_report_attestation import verify_recent_operator_reports


def _seed_repo(root: Path) -> None:
    (root / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (root / "glow/contracts/ci_baseline.json").write_text("{}\n", encoding="utf-8")


def _seed_integrity(root: Path) -> None:
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
        "gate_results": [],
        "primary_reason": "integrity_ok",
        "reason_stack": [],
        "recommended_actions": [],
        "policy_hash": "policy-hash",
        "budget_exhausted": False,
        "budget_remaining": {"verify_streams": 1},
    }
    write_json(root / "glow/forge/integrity/status_2099-01-01T00-00-00Z.json", payload)


def test_operator_status_report_written_and_cataloged(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_integrity(tmp_path)
    monkeypatch.chdir(tmp_path)

    rc = forge_status.main(["--json"])
    assert rc == 0

    artifacts = sorted((tmp_path / "glow/forge/operator/status").glob("status_*.json"), key=lambda p: p.name)
    assert artifacts
    payload = json.loads(artifacts[-1].read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["integrity_overall"] == "ok"

    entry = artifact_catalog.latest(tmp_path, "operator_status")
    assert entry is not None
    loaded = artifact_catalog.load_catalog_artifact(tmp_path, entry)
    assert loaded is not None
    assert loaded["policy_hash"] == "policy-hash"


def test_operator_replay_signed_hmac_and_verified(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_OPERATOR_REPORT_VERIFY", "1")

    rc = forge_replay.main(["--verify", "--last-n", "5", "--emit-snapshot", "0"])
    assert rc == 0

    replay_artifacts = sorted((tmp_path / "glow/forge/replay").glob("replay_*.json"), key=lambda p: p.name)
    assert replay_artifacts
    payload = json.loads(replay_artifacts[-1].read_text(encoding="utf-8"))
    assert payload["replay_mode"] is True

    verify = verify_recent_operator_reports(tmp_path, last=5)
    assert verify.ok is True


def test_status_latest_prints_consistency_when_replay_exists(tmp_path: Path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _seed_integrity(tmp_path)
    write_json(
        tmp_path / "glow/forge/replay/replay_2099-01-01T00-00-00Z.json",
        {
            "schema_version": 1,
            "ts": "2099-01-01T00:00:00Z",
            "replay_mode": True,
            "policy_hash": "policy-hash",
            "integrity_status_hash": "abc",
            "integrity_overall": "fail",
            "primary_reason": "x",
            "reason_stack": [],
            "verification_results": {},
            "inputs": {},
            "snapshot_emitted": False,
            "snapshot_emit_reason": "flag_disabled",
            "catalog_rebuild": {"status": "skipped", "reason": "catalog_exists"},
            "provenance": {},
            "exit_code": 1,
        },
    )
    append_jsonl(
        tmp_path / "pulse/artifact_catalog.jsonl",
        {
            "schema_version": 1,
            "ts": "2099-01-01T00:00:00Z",
            "kind": "operator_replay",
            "id": "2099-01-01T00:00:00Z",
            "path": "glow/forge/replay/replay_2099-01-01T00-00-00Z.json",
            "schema_name": "forge_replay_report",
            "schema_version_artifact": 1,
            "links": {},
            "summary": {},
        },
    )
    monkeypatch.chdir(tmp_path)

    forge_status.main(["--latest"])
    out = capsys.readouterr().out
    assert "tick_replay_consistency=" in out
