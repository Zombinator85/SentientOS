"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

import os
import pytest

if os.getenv("CI"):
    pytest.skip("skip cross-lang on CI", allow_module_level=True)

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import sys
import subprocess
from pathlib import Path

pytestmark = [pytest.mark.requires_node, pytest.mark.requires_go]

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from privilege_lint import LintConfig, PrivilegeLinter
from privilege_lint.js_rules import validate_js
from privilege_lint.go_rules import validate_go
from privilege_lint._compat import RuleSkippedError


def test_js_eval(tmp_path: Path) -> None:
    f = tmp_path / "demo.js"
    f.write_text("eval('1')", encoding="utf-8")
    try:
        issues = validate_js(f)
    except RuleSkippedError as exc:
        pytest.skip(str(exc))
    assert any("avoid eval" in m for m in issues)


def test_go_wrap(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "main.go"
    f.write_text("package main\nfunc main(){}", encoding="utf-8")

    def fake_run(cmd, capture_output=True, text=True, check=False):
        return subprocess.CompletedProcess(cmd, 1, "", "main.go:1: vet issue")

    monkeypatch.setattr(subprocess, "run", fake_run)
    try:
        issues = validate_go(f)
    except RuleSkippedError as exc:
        pytest.skip(str(exc))
    assert any("vet issue" in m for m in issues)


def test_baseline(tmp_path: Path) -> None:
    f = tmp_path / "t.py"
    f.write_text("print(1)\n", encoding="utf-8")
    base = tmp_path / ".plint_baseline.json"
    l = PrivilegeLinter(LintConfig(enforce_banner=False))
    issues = l.validate(f)
    if not issues:
        pytest.skip("no lint message")
    msg = issues[0]
    base.write_text("{" + f'"{msg}": true' + "}")
    cfg = LintConfig(enforce_banner=False, baseline_file=str(base))
    l2 = PrivilegeLinter(cfg)
    assert l2.validate(f) == []
