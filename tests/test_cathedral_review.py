import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos.cathedral import Amendment
from sentientos.cathedral.digest import CathedralDigest
from sentientos.cathedral.review import review_amendment


def _make_amendment(changes, **overrides):
    base = dict(
        id="review-001",
        created_at=datetime(2024, 3, 10, 15, 0, tzinfo=timezone.utc),
        proposer="codex",
        summary="Tune dashboard copy",
        changes=changes,
        reason="Keeps UI copy aligned with council guidance.",
    )
    base.update(overrides)
    return Amendment(**base)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    review_log = tmp_path / "cathedral_review.log"
    quarantine_dir = tmp_path / "quarantine"
    monkeypatch.setenv("SENTIENTOS_CATHEDRAL_REVIEW_LOG", str(review_log))
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_DIR", str(quarantine_dir))
    yield
    monkeypatch.delenv("SENTIENTOS_CATHEDRAL_REVIEW_LOG", raising=False)
    monkeypatch.delenv("SENTIENTOS_QUARANTINE_DIR", raising=False)


def test_review_accepts_clean_amendment(tmp_path):
    amendment = _make_amendment({"actions": ["document_change"]})
    result = review_amendment(amendment)
    assert result.status == "accepted"

    review_log = Path(os.getenv("SENTIENTOS_CATHEDRAL_REVIEW_LOG"))
    assert review_log.exists()
    entries = [json.loads(line) for line in review_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert entries[-1]["status"] == "accepted"

    digest = CathedralDigest.from_log(review_log)
    assert digest.accepted >= 1
    assert digest.quarantined == 0


def test_review_quarantines_unsafe_amendment(tmp_path):
    amendment = _make_amendment({"actions": ["direct_source_write"], "removed_fields": ["persona.safety_flags"]}, id="review-unsafe")
    result = review_amendment(amendment)
    assert result.status == "quarantined"
    assert result.quarantine_path

    quarantine_path = Path(result.quarantine_path)
    assert quarantine_path.exists()
    payload = json.loads(quarantine_path.read_text(encoding="utf-8"))
    assert payload["amendment"]["id"] == "review-unsafe"
    assert payload["errors"]

    review_log = Path(os.getenv("SENTIENTOS_CATHEDRAL_REVIEW_LOG"))
    entries = [json.loads(line) for line in review_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert entries[-1]["status"] == "quarantined"
    assert entries[-1]["quarantine_path"] == result.quarantine_path
