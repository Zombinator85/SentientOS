"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
from pathlib import Path

import audit_immutability as ai
import cleanup_audit as ca


def test_cleanup_directory(tmp_path: Path) -> None:
    d = tmp_path / "logs"
    d.mkdir()
    log = d / "log.jsonl"
    ai.append_entry(log, {"x": 1})
    log.write_text(log.read_text() + "{bad}\n", encoding="utf-8")
    results, percent = ca.cleanup_directory(d)
    assert list(results.keys()) == [str(log)]
    assert results[str(log)] == [2]
    assert percent == 50.0
