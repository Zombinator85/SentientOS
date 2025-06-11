import os, sys
from pathlib import Path

import sentientos.privilege_lint as pl
from sentientos.privilege_lint.config import LintConfig


def test_key_detection(tmp_path: Path) -> None:
    f = tmp_path / "key.py"
    f.write_text("AWS='AKIA1234567890ABCD1234'", encoding="utf-8")
    cfg = LintConfig(security_enabled=True, enforce_banner=False)
    linter = pl.PrivilegeLinter(cfg)
    issues = linter.validate(f)
    assert any("security-key" in i for i in issues)


def test_disable_comment(tmp_path: Path) -> None:
    f = tmp_path / "key.py"
    f.write_text("AWS='AKIA1234567890ABCD1234'  # plint: disable=security-key", encoding="utf-8")
    cfg = LintConfig(security_enabled=True, enforce_banner=False)
    linter = pl.PrivilegeLinter(cfg)
    assert linter.validate(f) == []
