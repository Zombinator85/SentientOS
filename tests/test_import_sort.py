"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os, sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl

CFG = """\
[lint]
enforce_banner = true
enforce_import_sort = true
fix_overwrite = true
"""


def setup_cfg(tmp_path: Path) -> None:
    (tmp_path / "privilege_lint.toml").write_text(CFG, encoding="utf-8")


def test_good_import_order(tmp_path: Path, monkeypatch) -> None:
    setup_cfg(tmp_path)
    (tmp_path / "localmod.py").write_text("", encoding="utf-8")
    lines = pl.DEFAULT_BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        '"""doc"""',
        'import os',
        '',
        'import yaml',
        '',
        'import localmod',
    ]
    f = tmp_path / "tool.py"
    f.write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    linter = pl.PrivilegeLinter()
    assert linter.validate(f) == []


def test_bad_import_order(tmp_path: Path, monkeypatch) -> None:
    setup_cfg(tmp_path)
    (tmp_path / "localmod.py").write_text("", encoding="utf-8")
    lines = pl.DEFAULT_BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        '"""doc"""',
        'import localmod',
        'import os',
        '',
        'import yaml',
    ]
    f = tmp_path / "tool.py"
    f.write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    linter = pl.PrivilegeLinter()
    assert linter.validate(f)


def test_autofix_import_sort(tmp_path: Path, monkeypatch) -> None:
    setup_cfg(tmp_path)
    (tmp_path / "localmod.py").write_text("", encoding="utf-8")
    lines = pl.DEFAULT_BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        '"""doc"""',
        'import yaml',
        'import os',
        '',
        'import localmod',
    ]
    f = tmp_path / "tool.py"
    f.write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    linter = pl.PrivilegeLinter()
    assert linter.apply_fix(f)
    fixed = f.read_text().splitlines()
    start = len(pl.BANNER_ASCII) + 2
    assert fixed[start:] == ['import os', '', 'import yaml', '', 'import localmod']
