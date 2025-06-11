"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os, sys
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl
from privilege_lint.config import LintConfig


def test_disable_import_sort(tmp_path: Path) -> None:
    f = tmp_path / "m.py"
    lines = pl.BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        "# plint: disable=import-sort",
        "import b",
        "import a",
    ]
    f.write_text("\n".join(lines), encoding="utf-8")
    cfg = LintConfig(enforce_import_sort=True, enforce_banner=False)
    linter = pl.PrivilegeLinter(cfg)
    assert linter.validate(f) == []
