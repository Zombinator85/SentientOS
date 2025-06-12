"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import orchestrator
import autonomous_reflector as ar
import time


def test_orchestrator_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    reload(orchestrator)
    called = []
    monkeypatch.setattr(ar, "run_once", lambda: called.append(True))
    o = orchestrator.Orchestrator(interval=0.01)
    o.run_cycle()
    assert called
    assert orchestrator.STATE_PATH.exists()


def test_orchestrator_start_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    reload(orchestrator)
    calls = []
    monkeypatch.setattr(ar, "run_once", lambda: calls.append(True))
    o = orchestrator.Orchestrator(interval=0.01)
    monkeypatch.setattr(time, "sleep", lambda x: None)
    o.start(cycles=2)
    assert len(calls) == 2
    o.stop()
    status = o.status()
    assert status["running"] is False
