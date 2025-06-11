"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os, sys
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl
from privilege_lint.config import LintConfig


def test_google_style(tmp_path: Path) -> None:
    file = tmp_path / "mod.py"
    file.write_text("\n".join(pl.BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        'def foo(x):\n    """Doc.\n\n    Args:\n        x: value\n    """\n    return x'
    ]), encoding="utf-8")
    cfg = LintConfig(docstrings_enforce=True)
    linter = pl.PrivilegeLinter(cfg)
    assert linter.validate(file) == []


def test_missing_stub(tmp_path: Path) -> None:
    file = tmp_path / "bad.py"
    file.write_text("\n".join(pl.BANNER_ASCII + [pl.FUTURE_IMPORT, 'def foo():\n    pass']), encoding="utf-8")
    cfg = LintConfig(docstrings_enforce=True, docstring_insert_stub=True)
    linter = pl.PrivilegeLinter(cfg)
    assert linter.validate(file)
    linter.apply_fix(file)
    assert '"""TODO:' in file.read_text()
