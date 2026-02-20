from __future__ import annotations

import json
from pathlib import Path

from sentientos.doctrine_identity import verify_doctrine_identity


def test_verify_doctrine_identity_enforce_fails_on_mismatch(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_DOCTRINE_IDENTITY_ENFORCE", "1")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/contract_manifest.json").write_text(json.dumps({"bundle_sha256": "local"}) + "\n", encoding="utf-8")
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_1.json").write_text(
        json.dumps({"doctrine_identity": {"bundle_sha256": "remote"}}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, payload = verify_doctrine_identity(tmp_path)

    assert ok is False
    assert payload["mismatch"] is True


def test_verify_doctrine_identity_warn_only(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("SENTIENTOS_DOCTRINE_IDENTITY_ENFORCE", raising=False)
    monkeypatch.setenv("SENTIENTOS_DOCTRINE_IDENTITY_WARN", "1")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/contract_manifest.json").write_text(json.dumps({"bundle_sha256": "local"}) + "\n", encoding="utf-8")
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_1.json").write_text(
        json.dumps({"doctrine_identity": {"bundle_sha256": "remote"}}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, payload = verify_doctrine_identity(tmp_path)

    assert ok is True
    assert payload["warn_only"] is True
