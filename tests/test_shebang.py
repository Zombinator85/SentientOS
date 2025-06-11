import os, sys
from pathlib import Path


import sentientos.privilege_lint as pl
from sentientos.privilege_lint.shebang_rules import SHEBANG


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

