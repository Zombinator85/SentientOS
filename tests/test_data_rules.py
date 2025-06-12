"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os, sys, json
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from privilege_lint.data_rules import validate_json, validate_csv


def test_json_fix(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text('{"badKey": 1,}', encoding="utf-8")
    issues = validate_json(p, fix=True)
    assert any("snake_case" in m for m in issues)
    p.write_text('{"good_key": 1,}', encoding="utf-8")
    issues = validate_json(p, fix=True)
    assert issues == []
    data = json.loads(p.read_text())
    assert "good_key" in data


def test_csv_columns(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    p.write_text("a,b\n1,2,3\n", encoding="utf-8")
    issues = validate_csv(p)
    assert any("expected" in i for i in issues)
