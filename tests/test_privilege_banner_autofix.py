"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import os
from pathlib import Path
from admin_utils import require_admin_banner


def test_autofix(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVILEGE_AUDIT_LOG", str(tmp_path / "log.jsonl"))
    import privilege_banner_autofix as pba
    importlib.reload(pba)
    target = tmp_path / "tool_cli.py"
    target.write_text("import os\nprint('hi')\n", encoding="utf-8")
    res = pba.autofix(target)
    assert res == "fixed"
    pba.log_result(target, res)
    data = target.read_text()
    assert "Sanctuary Privilege Ritual" in data
    assert "require_admin_banner()" in data
    log_lines = (tmp_path / "log.jsonl").read_text().splitlines()
    assert len(log_lines) == 1
