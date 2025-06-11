import os, sys
from pathlib import Path
import importlib.metadata as imd
from importlib.metadata import EntryPoint


import sentientos.privilege_lint as pl
from sentientos.privilege_lint.config import LintConfig


def test_plugin_runs(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "demo.txt"
    f.write_text("slug text", encoding="utf-8")
    ep = EntryPoint(name="slug", value="examples.slug_rule:validate", group="privilege_lint.plugins")
    monkeypatch.setattr(pl.plugins, "entry_points", lambda: {"privilege_lint.plugins": [ep]})
    linter = pl.PrivilegeLinter(LintConfig(enforce_banner=False))
    issues = linter.validate(f)
    assert any("slug word" in i for i in issues)
