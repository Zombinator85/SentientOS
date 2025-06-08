import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import scripts.ci_self_check as ci

class Dummy:
    def __init__(self, ret=0):
        self.returncode = ret

def test_ci_success(monkeypatch):
    calls = []
    def fake_run(cmd, env=None):
        calls.append(cmd)
        return Dummy(0)
    monkeypatch.setattr(ci.subprocess, "run", fake_run)
    assert ci.main([]) == 0
    assert len(calls) == 5

def test_ci_failure(monkeypatch):
    def fake_run(cmd, env=None):
        return Dummy(1)
    monkeypatch.setattr(ci.subprocess, "run", fake_run)
    assert ci.main([]) == 1
