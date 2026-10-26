"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from __future__ import annotations


import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import runpy
import pytest

class Dummy:
    def __init__(self, ret=0):
        self.returncode = ret

def _stub_privilege_for_unit_test(monkeypatch):
    import sentientos.privilege as privilege
    monkeypatch.setattr(privilege, "require_admin_banner", lambda: None)
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: None)

@pytest.mark.no_legacy_skip
def test_ci_success(monkeypatch):
    _stub_privilege_for_unit_test(monkeypatch)
    calls = []
    def fake_run(cmd, *, shell, check, **kw):
        calls.append((cmd, shell, check, kw))
        return Dummy(0)
    import builtins
    import subprocess as sp
    monkeypatch.setattr(sp, "run", fake_run)
    runpy.run_path("scripts/ci_self_check.py", run_name="__main__")
    assert len(calls) == 5
    assert all(isinstance(argv, list) and shell is False and check is True for argv, shell, check, _ in calls)
    assert [argv for argv, *_ in calls] == [
        ["python", "scripts/ritual_enforcer.py", "--fix"],
        ["python", "-m", "scripts.verify_audits", "logs/", "--auto-repair"],
        ["python", "-m", "pip", "install", "-e", ".[dev]"],
        ["mypy", "--strict", "--exclude", "tests", "sentientos"],
        ["python", "-m", "scripts.run_tests", "-q", "-m", "not env"],
    ]

@pytest.mark.no_legacy_skip
def test_ci_failure(monkeypatch):
    _stub_privilege_for_unit_test(monkeypatch)
    import subprocess as sp
    def fake_run(cmd, *, shell, check, **kw):
        assert isinstance(cmd, list)
        assert shell is False
        assert check is True
        raise sp.CalledProcessError(1, cmd)
    import builtins
    monkeypatch.setattr(sp, "run", fake_run)
    with pytest.raises(sp.CalledProcessError):
        runpy.run_path("scripts/ci_self_check.py", run_name="__main__")
