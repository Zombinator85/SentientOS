from __future__ import annotations

import json
from pathlib import Path

from scripts import bootstrap_trust_restore


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _entry(ts: str, data: dict[str, object], prev_hash: str) -> dict[str, object]:
    import hashlib

    h = hashlib.sha256()
    h.update(ts.encode("utf-8"))
    h.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    h.update(prev_hash.encode("utf-8"))
    digest = h.hexdigest()
    return {"timestamp": ts, "data": data, "prev_hash": prev_hash, "rolling_hash": digest}


def _seed_workspace(root: Path) -> None:
    _write_json(root / "vow/immutable_manifest.json", {"schema_version": 1, "files": []})
    (root / "vow/invariants.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "vow/invariants.yaml").write_text("version: 1\n", encoding="utf-8")

    (root / "logs").mkdir(parents=True, exist_ok=True)
    valid = _entry("2026-01-01T00:00:00Z", {"ok": True}, "0" * 64)
    broken = {
        "timestamp": "2026-01-01T00:00:01Z",
        "data": {"ok": False},
        "prev_hash": "bad",
        "rolling_hash": "bad",
    }
    (root / "logs/privileged_audit.jsonl").write_text(json.dumps(valid) + "\n" + json.dumps(broken) + "\n", encoding="utf-8")


def test_bootstrap_restores_missing_constitution_artifacts(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)

    report = bootstrap_trust_restore.run_bootstrap(tmp_path, reason="test-bootstrap", create_checkpoint=True)

    assert not report["still_missing_artifacts"]
    assert "glow/runtime/audit_trust_state.json" in report["bootstrapped_artifacts"]
    assert "glow/governor/rollup.json" in report["bootstrapped_artifacts"]
    assert report["constitution"]["state"] in {"restricted", "degraded", "healthy"}

    provenance = report["provenance"]
    assert any(item["artifact"] == "pulse_trust_epoch" for item in provenance)
    assert any(item["artifact"] == "federation_governance_digest" for item in provenance)


def test_bootstrap_creates_explicit_checkpoint_without_rewriting_history(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_workspace(tmp_path)
    original = (tmp_path / "logs/privileged_audit.jsonl").read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    report = bootstrap_trust_restore.run_bootstrap(tmp_path, reason="test-reanchor", create_checkpoint=True)

    checkpoint = report["checkpoint"]
    assert checkpoint["status"] == "created"
    assert checkpoint["path"] == "glow/forge/audit_reports/audit_recovery_checkpoints.jsonl"
    assert (tmp_path / checkpoint["path"]).exists()
    assert (tmp_path / "logs/privileged_audit.jsonl").read_text(encoding="utf-8") == original

    audit_after = report["audit_chain_after"]
    assert audit_after["recovery_state"]["history_state"] == "broken_preserved"
    assert audit_after["recovery_state"]["checkpoint_id"]
