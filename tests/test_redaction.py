import json
from pathlib import Path

import pytest

from sentientos.config import PrivacyConfig, PrivacyRedactionConfig
from sentientos.privacy import PrivacyManager


def test_log_redactor_masks_sensitive_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    config = PrivacyConfig(
        redactions=PrivacyRedactionConfig(enable=True),
        hash_pii=False,
    )
    manager = PrivacyManager(config)
    message = "Contact foo@example.com using Bearer tokentesttokentesttokentest"
    result = manager.redact_log(message)
    assert "[REDACTED]" in result.text
    assert "foo@example.com" in result.redacted_tokens


def test_hash_capsule_records_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    config = PrivacyConfig(
        redactions=PrivacyRedactionConfig(enable=True),
        hash_pii=True,
    )
    manager = PrivacyManager(config)
    capsule = {"text": "Reach me at pii@example.com"}
    hashed = manager.hash_capsule(capsule)
    assert hashed["text"].startswith("pii::") or "pii::" in hashed["text"]
    vault = tmp_path / "vow" / "keys" / "pii_vault.jsonl"
    assert vault.exists()
    lines = [json.loads(line) for line in vault.read_text(encoding="utf-8").splitlines() if line]
    assert any(entry["token"] == "pii@example.com" for entry in lines)
