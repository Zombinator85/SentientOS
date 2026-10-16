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
import sys
from pathlib import Path

import avatar_presence_cli as ap
import avatar_gallery_cli as ag


def test_gallery_listing(tmp_path, monkeypatch, capsys):
    log = tmp_path / "presence.jsonl"
    monkeypatch.setenv("AVATAR_PRESENCE_LOG", str(log))
    importlib.reload(ap)
    importlib.reload(ag)
    ap.log_invocation("a.blend", "ritual")
    monkeypatch.setattr(sys, "argv", ["gallery"])
    ag.main()
    out = capsys.readouterr().out
    assert "a.blend" in out


