"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os, sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl


def test_autofix_inserts_banner(tmp_path: Path) -> None:
    file = tmp_path / "tool.py"
    file.write_text(f"{pl.FUTURE_IMPORT}\n'\"doc\"'\n", encoding="utf-8")
    linter = pl.PrivilegeLinter()
    linter.apply_fix(file)
    lines = file.read_text().splitlines()
    assert lines[0] == pl.BANNER_ASCII[0]


def test_autofix_moves_future(tmp_path: Path) -> None:
    file = tmp_path / "tool.py"
    content = "\n".join(pl.BANNER_ASCII + ['"doc"', pl.FUTURE_IMPORT, 'import os'])
    file.write_text(content, encoding="utf-8")
    linter = pl.PrivilegeLinter()
    linter.apply_fix(file)
    lines = file.read_text().splitlines()
    assert lines[len(pl.BANNER_ASCII)] == pl.FUTURE_IMPORT


def test_directory_scan(tmp_path: Path) -> None:
    sub = tmp_path / "pkg"
    sub.mkdir()
    f = sub / "bad.py"
    f.write_text("import os\n'\"doc\"'\n", encoding="utf-8")
    rc = pl.main([str(tmp_path), "--quiet"])
    assert rc == 1
