"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os, sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl
from privilege_lint.shebang_rules import SHEBANG


def test_shebang_autofix(tmp_path: Path) -> None:
    file = tmp_path / "tool.py"
    file.write_text(f"{pl.FUTURE_IMPORT}\n", encoding="utf-8")
    file.chmod(0o644)
    cfg = pl.LintConfig(shebang_require=True, shebang_fix_mode=True)
    linter = pl.PrivilegeLinter(cfg)
    linter.apply_fix(file)
    lines = file.read_text().splitlines()
    assert lines[0] == SHEBANG
    assert os.access(file, os.X_OK)


def test_shebang_validate(tmp_path: Path) -> None:
    file = tmp_path / "tool.py"
    file.write_text(f"{pl.FUTURE_IMPORT}\n", encoding="utf-8")
    file.chmod(0o755)
    cfg = pl.LintConfig(shebang_require=True)
    linter = pl.PrivilegeLinter(cfg)
    issues = linter.validate(file)
    assert any("invalid shebang" in i for i in issues)

