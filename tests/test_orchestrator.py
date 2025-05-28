import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import orchestrator
import autonomous_reflector as ar


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
