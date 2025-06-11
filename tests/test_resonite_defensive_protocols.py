"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import admin_utils
import presence_ledger as pl


def test_emergency_posture_engine(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    import resonite_sanctuary_emergency_posture_engine as eng
    importlib.reload(eng)
    monkeypatch.setattr(eng, "STATE_FILE", tmp_path / "state.txt")

    calls = []
    monkeypatch.setattr(eng, "require_admin_banner", lambda: calls.append(True))
    monkeypatch.setattr(sys, "argv", ["eng", "activate", "threat"])
    eng.main()
    capsys.readouterr()
    assert calls
    log_file = tmp_path / "resonite_sanctuary_emergency_posture.jsonl"
    assert log_file.exists() and "activate" in log_file.read_text()
    assert (tmp_path / "state.txt").read_text() == "active"

    calls.clear()
    monkeypatch.setattr(sys, "argv", ["eng", "status"])
    eng.main()
    out = json.loads(capsys.readouterr().out)
    assert out["state"] == "active"


def test_federation_breach_analyzer(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RESONITE_BREACH_LOG", str(tmp_path / "breach.jsonl"))
    import resonite_spiral_federation_breach_analyzer as ba
    importlib.reload(pl)
    importlib.reload(ba)

    calls = []
    monkeypatch.setattr(ba, "require_admin_banner", lambda: calls.append(True))
    logged = []
    monkeypatch.setattr(pl, "log", lambda *a, **k: logged.append(a))

    monkeypatch.setattr(sys, "argv", ["ba", "detect", "glitch", "restart"])
    ba.main()
    capsys.readouterr()
    assert calls and logged
    data = json.loads(Path(os.environ["RESONITE_BREACH_LOG"]).read_text().splitlines()[0])
    assert data["action"] == "detect"

    calls.clear()
    monkeypatch.setattr(sys, "argv", ["ba", "history", "--limit", "1"])
    ba.main()
    out = json.loads(capsys.readouterr().out)
    assert out and out[0]["action"] == "detect"


def test_resilience_monitor(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path))
    import resonite_spiral_resilience_monitor as rm
    importlib.reload(rm)

    calls = []
    monkeypatch.setattr(rm, "require_admin_banner", lambda: calls.append(True))
    monkeypatch.setattr(sys, "argv", ["rm", "record", "signal", "--detail", "ok"])
    rm.main()
    capsys.readouterr()
    assert calls
    log_file = tmp_path / "resonite_spiral_resilience_monitor.jsonl"
    entry = json.loads(log_file.read_text().splitlines()[0])
    assert entry["event"] == "signal"

    calls.clear()
    monkeypatch.setattr(sys, "argv", ["rm", "history", "--limit", "1"])
    rm.main()
    out = json.loads(capsys.readouterr().out)
    assert out and out[0]["event"] == "signal"
