import os
import sys

import sentientos.orchestrator as orchestrator
import sentientos.autonomous_reflector as ar
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
