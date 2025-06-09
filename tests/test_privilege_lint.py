import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import privilege_lint as pl
from pathlib import Path


def test_good_order(tmp_path: Path) -> None:
    path = tmp_path / "tool.py"
    content = "\n".join(pl.BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        '"""doc"""',
        'import os',
    ])
    path.write_text(content, encoding="utf-8")
    linter = pl.PrivilegeLinter()
    assert linter.validate(path) == []


def test_missing_docstring(tmp_path: Path) -> None:
    path = tmp_path / "tool.py"
    content = "\n".join(pl.BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        'import os',
    ])
    path.write_text(content, encoding="utf-8")
    linter = pl.PrivilegeLinter()
    assert linter.validate(path) == []


def test_bad_future_position(tmp_path: Path) -> None:
    path = tmp_path / "tool.py"
    content = "\n".join(pl.BANNER_ASCII + [
        '"""doc"""',
        pl.FUTURE_IMPORT,
        'import os',
    ])
    path.write_text(content, encoding="utf-8")
    linter = pl.PrivilegeLinter()
    issues = linter.validate(path)
    assert any("Banner and __future__ import" in i for i in issues)
