"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import runpy
import pytest

class Dummy:
    def __init__(self, ret=0):
        self.returncode = ret

def test_ci_success(monkeypatch):
    calls = []
    def fake_run(cmd, shell=True, check=True, **kw):
        calls.append(cmd)
        return Dummy(0)
    import builtins
    import subprocess as sp
    monkeypatch.setattr(sp, "run", fake_run)
    runpy.run_path("scripts/ci_self_check.py", run_name="__main__")
    assert len(calls) == 5
    assert "python -m pip install -e ." in calls

def test_ci_failure(monkeypatch):
    import subprocess as sp
    def fake_run(cmd, shell=True, check=True, **kw):
        raise sp.CalledProcessError(1, cmd)
    import builtins
    monkeypatch.setattr(sp, "run", fake_run)
    with pytest.raises(sp.CalledProcessError):
        runpy.run_path("scripts/ci_self_check.py", run_name="__main__")
