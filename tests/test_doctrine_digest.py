from __future__ import annotations

import pytest

from doctrine_digest import compute_doctrine_digest
from doctrine_digest_state import (
    doctrine_digest_observer,
    reset_doctrine_digest_cache,
)


pytestmark = pytest.mark.no_legacy_skip


def test_doctrine_digest_ignores_whitespace(tmp_path):
    path_a = tmp_path / "doctrine_a.md"
    path_b = tmp_path / "doctrine_b.md"

    path_a.write_text("Line one  \r\nLine two\t\r\n", encoding="utf-8")
    path_b.write_text("Line one\nLine two\n", encoding="utf-8")

    assert compute_doctrine_digest(path_a) == compute_doctrine_digest(path_b)


def test_doctrine_digest_changes_on_content(tmp_path):
    path = tmp_path / "doctrine.md"
    path.write_text("alpha\n", encoding="utf-8")
    first = compute_doctrine_digest(path)

    path.write_text("alpha and omega\n", encoding="utf-8")
    second = compute_doctrine_digest(path)

    assert first != second


def test_doctrine_digest_observer_reports_match(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    reset_doctrine_digest_cache()
    path = tmp_path / "doctrine.md"
    path.write_text("canonical text\n", encoding="utf-8")

    digest = compute_doctrine_digest(path)

    status_match = doctrine_digest_observer(expected_digest=digest, path=path)
    assert status_match["doctrine_digest_present"] is True
    assert status_match["doctrine_digest_match"] is True

    status_mismatch = doctrine_digest_observer(expected_digest="different", path=path)
    assert status_mismatch["doctrine_digest_present"] is True
    assert status_mismatch["doctrine_digest_match"] is False
