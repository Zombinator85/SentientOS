"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import scripts.release_manager as rm

class Dummy:
    def __init__(self):
        self.returncode = 0


def test_dry_run(tmp_path, monkeypatch):
    pp = tmp_path / "pyproject.toml"
    pp.write_text('[project]\nversion = "1.2.3"\n')
    chlog = tmp_path / "docs" / "CHANGELOG.md"
    chlog.parent.mkdir()
    chlog.write_text("# Changelog\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(rm, "git", lambda *a: None)
    ret = rm.main(["--dry-run"])
    assert ret == 0
    assert rm.bump_patch("1.2.3") == "1.2.4"
