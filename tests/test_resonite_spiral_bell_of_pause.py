"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import admin_utils


def test_bell_of_pause_cli(tmp_path, monkeypatch, capsys):
    bell_log = tmp_path / "bell.jsonl"
    monkeypatch.setenv("RESONITE_BELL_PAUSE_LOG", str(bell_log))

    import resonite_spiral_bell_of_pause as rbp
    importlib.reload(rbp)

    calls = []
    monkeypatch.setattr(rbp, "require_admin_banner", lambda: calls.append(True))

    monkeypatch.setattr(sys, "argv", ["bell", "pause", "maintenance", "WorldA"])
    rbp.main()
    capsys.readouterr()
    assert calls
    data = json.loads(bell_log.read_text().splitlines()[0])
    assert data["action"] == "pause" and data["world"] == "WorldA"

    calls.clear()
    monkeypatch.setattr(sys, "argv", ["bell", "resolve", "WorldA"])
    rbp.main()
    capsys.readouterr()
    assert calls
    lines = bell_log.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[1])["action"] == "resolve"

    calls.clear()
    monkeypatch.setattr(sys, "argv", ["bell", "history", "--limit", "2"])
    rbp.main()
    out = json.loads(capsys.readouterr().out)
    assert len(out) == 2 and out[0]["action"] == "pause"
