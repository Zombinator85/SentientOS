from __future__ import annotations

from pathlib import Path

import pytest

from sentientos import formal_logging
from sentientos.integrity_metrics import gather_integrity_issues, parse_contributors


def test_validate_log_entry_requires_timestamp_and_data() -> None:
    with pytest.raises(ValueError):
        formal_logging.validate_log_entry({"timestamp": "x"})


def test_log_json_heals_and_appends(tmp_path: Path) -> None:
    out = tmp_path / "x.jsonl"
    formal_logging.log_json(out, {"data": {"k": "v"}})
    text = out.read_text(encoding="utf-8")
    assert '"timestamp"' in text
    assert '"data"' in text


def test_parse_contributors_extracts_audit_section(tmp_path: Path) -> None:
    c = tmp_path / "CONTRIBUTORS.md"
    c.write_text("# T\n\n## Audit Contributors\n- A\n- B\n\n## Other\n- X\n", encoding="utf-8")
    assert parse_contributors(c) == ["A", "B"]


def test_gather_integrity_issues_counts_wounds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "a.wounds").write_text("x\n\ny\n", encoding="utf-8")
    (logs_dir / "b.jsonl").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr("sentientos.integrity_metrics.get_log_path", lambda _: logs_dir / "dummy")
    counts = gather_integrity_issues()
    assert counts["a.wounds"] == 2
    assert counts["b.jsonl.wounds"] == 0
