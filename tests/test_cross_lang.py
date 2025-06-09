import os, sys, subprocess
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from privilege_lint import LintConfig, PrivilegeLinter
from privilege_lint.js_rules import validate_js
from privilege_lint.go_rules import validate_go


def test_js_eval(tmp_path: Path) -> None:
    f = tmp_path / "demo.js"
    f.write_text("eval('1')", encoding="utf-8")
    issues = validate_js(f)
    assert any("avoid eval" in m for m in issues)


def test_go_wrap(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "main.go"
    f.write_text("package main\nfunc main(){}", encoding="utf-8")

    def fake_run(cmd, capture_output=True, text=True, check=False):
        return subprocess.CompletedProcess(cmd, 1, "", "main.go:1: vet issue")

    monkeypatch.setattr(subprocess, "run", fake_run)
    issues = validate_go(f)
    assert any("vet issue" in m for m in issues)


def test_baseline(tmp_path: Path) -> None:
    f = tmp_path / "t.py"
    f.write_text("print(1)\n", encoding="utf-8")
    base = tmp_path / ".plint_baseline.json"
    l = PrivilegeLinter(LintConfig(enforce_banner=False))
    msg = l.validate(f)[0]
    base.write_text("{" + f'"{msg}": true' + "}")
    cfg = LintConfig(enforce_banner=False, baseline_file=str(base))
    l2 = PrivilegeLinter(cfg)
    assert l2.validate(f) == []
