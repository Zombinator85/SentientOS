import os, sys
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl
from privilege_lint.config import LintConfig


def test_template_unbalanced(tmp_path: Path) -> None:
    f = tmp_path / "bad.j2"
    f.write_text("{% if name %}hello", encoding="utf-8")
    cfg = LintConfig(templates_enabled=True, templates_context=["name"], enforce_banner=False)
    linter = pl.PrivilegeLinter(cfg)
    issues = linter.validate(f)
    assert any("unbalanced" in i for i in issues)


def test_template_ok(tmp_path: Path) -> None:
    f = tmp_path / "ok.j2"
    f.write_text("# context: name\nHello {{ name }}", encoding="utf-8")
    cfg = LintConfig(templates_enabled=True, enforce_banner=False)
    linter = pl.PrivilegeLinter(cfg)
    assert linter.validate(f) == []
