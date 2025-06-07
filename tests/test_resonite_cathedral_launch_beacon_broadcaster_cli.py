from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import os
import sys
import importlib
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import admin_utils
import presence_ledger as pl


def test_resonite_beacon_cli(tmp_path, monkeypatch, capsys):
    beacon = tmp_path / "beacon.jsonl"
    presence = tmp_path / "presence.jsonl"
    monkeypatch.setenv("RESONITE_BEACON_LOG", str(beacon))
    monkeypatch.setenv("USER_PRESENCE_LOG", str(presence))

    import resonite_cathedral_launch_beacon_broadcaster as rcl
    importlib.reload(pl)
    importlib.reload(rcl)

    monkeypatch.setattr(pl, "log", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(rcl, "require_admin_banner", lambda: calls.append(True))

    monkeypatch.setattr(sys, "argv", ["beacon", "launch", "Ada"])
    rcl.main()
    assert calls and beacon.exists() and len(beacon.read_text().splitlines()) == 1
    capsys.readouterr()  # clear launch output

    calls.clear()
    monkeypatch.setattr(sys, "argv", ["beacon", "history", "--limit", "1"])
    rcl.main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert calls and data and data[0]["action"] == "launch"

