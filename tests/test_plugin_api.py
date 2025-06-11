"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os, sys
from pathlib import Path
import importlib.metadata as imd
from importlib.metadata import EntryPoint

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl
from privilege_lint.config import LintConfig


def test_plugin_runs(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "demo.txt"
    f.write_text("slug text", encoding="utf-8")
    ep = EntryPoint(name="slug", value="examples.slug_rule:validate", group="privilege_lint.plugins")
    monkeypatch.setattr(pl.plugins, "entry_points", lambda: {"privilege_lint.plugins": [ep]})
    linter = pl.PrivilegeLinter(LintConfig(enforce_banner=False))
    issues = linter.validate(f)
    assert any("slug word" in i for i in issues)
