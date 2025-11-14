import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.cathedral import Amendment
from sentientos.cathedral.quarantine import quarantine_amendment


@pytest.fixture(autouse=True)
def _quarantine_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "quarantine"
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_DIR", str(target))
    yield
    monkeypatch.delenv("SENTIENTOS_QUARANTINE_DIR", raising=False)


def test_quarantine_saves_payload(tmp_path: Path):
    amendment = Amendment(
        id="quarantine-001",
        created_at=datetime(2024, 4, 4, 12, 0, tzinfo=timezone.utc),
        proposer="codex",
        summary="Test quarantine",
        changes={"actions": ["direct_source_write"]},
        reason="Ensure quarantine path persists",
    )
    path = quarantine_amendment(amendment, ["Invariant violation"])
    stored = Path(path)
    assert stored.exists()
    payload_text = stored.read_text(encoding="utf-8")
    payload = json.loads(payload_text)
    assert payload["amendment"]["id"] == "quarantine-001"
    assert payload["errors"] == ["Invariant violation"]
    assert payload["digest"]
    assert payload["proposer"] == "codex"

    second = quarantine_amendment(amendment, ["Invariant violation"])
    assert second == path
    assert stored.read_text(encoding="utf-8") == payload_text
