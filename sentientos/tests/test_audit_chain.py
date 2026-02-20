from __future__ import annotations

import json
from pathlib import Path

from sentientos.audit_chain_gate import verify_audit_chain
from scripts import audit_chain_doctor
from scripts import verify_audits


def _entry(ts: str, data: dict[str, object], prev_hash: str) -> dict[str, object]:
    import hashlib

    h = hashlib.sha256()
    h.update(ts.encode("utf-8"))
    h.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    h.update(prev_hash.encode("utf-8"))
    digest = h.hexdigest()
    return {"timestamp": ts, "data": data, "prev_hash": prev_hash, "rolling_hash": digest}


def test_verify_audit_chain_ok(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    e1 = _entry("2026-01-01T00:00:00Z", {"a": 1}, "0" * 64)
    e2 = _entry("2026-01-01T00:00:01Z", {"a": 2}, str(e1["rolling_hash"]))
    (tmp_path / "logs/audit.jsonl").write_text(json.dumps(e1) + "\n" + json.dumps(e2) + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert verify_audits.main(["--strict"]) == 0
    result = verify_audit_chain(tmp_path)
    assert result.ok is True


def test_verify_audit_chain_broken_has_first_break(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    bad = {"timestamp": "2026-01-01T00:00:00Z", "data": {"a": 1}, "prev_hash": "bad", "rolling_hash": "bad"}
    (tmp_path / "logs/audit.jsonl").write_text(json.dumps(bad) + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert verify_audits.main(["--strict"]) == 1
    reports = sorted((tmp_path / "glow/forge/audit_reports").glob("audit_chain_report_*.json"))
    assert reports
    payload = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert payload["status"] == "broken"
    assert isinstance(payload["first_break"], dict)


def test_audit_chain_doctor_index_repair_and_refusal(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_a.json").write_text(
        json.dumps({"receipt_id": "a", "created_at": "2026-01-01T00:00:00Z", "receipt_hash": "h1", "prev_receipt_hash": None}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/forge/receipts/receipts_index.jsonl").write_text("{}\n", encoding="utf-8")

    assert audit_chain_doctor.main(["--repair-index-only"]) == 0
    report_paths = sorted((tmp_path / "glow/forge/audit_reports").glob("audit_doctor_*.json"))
    assert report_paths
    repaired = json.loads(report_paths[-1].read_text(encoding="utf-8"))
    assert repaired["actions"]

    assert audit_chain_doctor.main(["--truncate-after-break"]) == 1
    report_paths = sorted((tmp_path / "glow/forge/audit_reports").glob("audit_doctor_*.json"))
    refused = json.loads(report_paths[-1].read_text(encoding="utf-8"))
    assert refused["refused"]
