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
from privilege_lint.config import LintConfig


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
