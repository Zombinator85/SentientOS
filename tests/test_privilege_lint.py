"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


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


def test_main_block_in_tests_scanned(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "cli.py"
    f.write_text('if __name__ == "__main__":\n    pass\n', encoding="utf-8")
    rc = pl.main([str(tmp_path), "--quiet"])
    assert rc == 1


def test_argparse_usage_in_tests_scanned(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "cli.py"
    f.write_text('import argparse\nargparse.ArgumentParser()\n', encoding="utf-8")
    rc = pl.main([str(tmp_path), "--quiet"])
    assert rc == 1


def test_banner_missing_failure(tmp_path: Path) -> None:
    path = tmp_path / "tool_cli.py"
    path.write_text("\n".join([
        pl.FUTURE_IMPORT,
        "import argparse",
        "if __name__ == \"__main__\":",
        "    argparse.ArgumentParser().parse_args()",
    ]), encoding="utf-8")
    linter = pl.PrivilegeLinter()
    issues = linter.validate(path)
    assert any("banner" in i.lower() for i in issues)


def test_missing_admin_call(tmp_path: Path) -> None:
    path = tmp_path / "tool_cli.py"
    content = pl.BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        "import argparse",
        "if __name__ == \"__main__\":",
        "    argparse.ArgumentParser().parse_args()",
    ]
    path.write_text("\n".join(content), encoding="utf-8")
    linter = pl.PrivilegeLinter()
    issues = linter.validate(path)
