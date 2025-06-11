import os, sys
from pathlib import Path


import sentientos.privilege_lint as pl


def _mk_file(tmp_path: Path, text: str) -> Path:
    file = tmp_path / "mod.py"
    file.write_text("\n".join(pl.BANNER_ASCII + [pl.FUTURE_IMPORT, text]), encoding="utf-8")
    return file


def test_type_hint_violation(tmp_path: Path) -> None:
    cfg = pl.LintConfig(enforce_type_hints=True)
    linter = pl.PrivilegeLinter(cfg)
    path = _mk_file(tmp_path, "def foo(x): return x")
    issues = linter.validate(path)
    assert any("missing type hints" in i for i in issues)


def test_type_hint_ok(tmp_path: Path) -> None:
    cfg = pl.LintConfig(enforce_type_hints=True)
    linter = pl.PrivilegeLinter(cfg)
    path = _mk_file(tmp_path, "def foo(x: int) -> int: return x")
    assert linter.validate(path) == []
