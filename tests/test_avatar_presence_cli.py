#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/
from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""



import importlib
from pathlib import Path

import avatar_presence_cli as ap


def test_log_invocation(tmp_path, monkeypatch, capsys):
    log = tmp_path / "presence.jsonl"
    monkeypatch.setenv("AVATAR_PRESENCE_LOG", str(log))
    importlib.reload(ap)
    ap.log_invocation("a.blend", "test", "visual")
    assert log.exists()
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    data = ap.log_invocation("a.blend", "test2")
    assert data["reason"] == "test2"

