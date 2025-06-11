import os, sys
from pathlib import Path

import sentientos.privilege_lint as pl
from sentientos.privilege_lint.config import LintConfig


def test_license_insertion(tmp_path: Path) -> None:
    f = tmp_path / "script.py"
    f.write_text("\n".join(["#!/usr/bin/env python3", "print('hi')"]), encoding="utf-8")
    cfg = LintConfig(license_header="# SPDX-License-Identifier: MIT")
    linter = pl.PrivilegeLinter(cfg, project_root=tmp_path)
    assert linter.validate(f)
    linter.apply_fix(f)
    text = f.read_text()
    assert "SPDX-License-Identifier" in text
