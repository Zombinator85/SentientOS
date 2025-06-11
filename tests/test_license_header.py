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


def test_license_insertion(tmp_path: Path) -> None:
    f = tmp_path / "script.py"
    f.write_text("\n".join(["#!/usr/bin/env python3", "print('hi')"]), encoding="utf-8")
    cfg = LintConfig(license_header="# SPDX-License-Identifier: MIT")
    linter = pl.PrivilegeLinter(cfg, project_root=tmp_path)
    assert linter.validate(f)
    linter.apply_fix(f)
    text = f.read_text()
    assert "SPDX-License-Identifier" in text
