"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()


import os
import sys
import importlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import admin_utils


def test_avatar_autonomous_scheduler_cli(tmp_path, monkeypatch):
    req = tmp_path / "requests.jsonl"
    apv = tmp_path / "approved.jsonl"
    monkeypatch.setenv("AVATAR_RITUAL_REQUEST_LOG", str(req))
    monkeypatch.setenv("AVATAR_RITUAL_APPROVAL_LOG", str(apv))

    import avatar_autonomous_ritual_scheduler as ars
    importlib.reload(ars)

    calls = []
    monkeypatch.setattr(sys, "argv", ["ars", "request", "Bob", "dance"])
    ars.main()
    assert calls and calls[-1] is True
    assert req.exists() and len(req.read_text().splitlines()) == 1

    calls.clear()
    monkeypatch.setattr(sys, "argv", ["ars", "approve", "0"])
    ars.main()
    assert calls and len(calls) == 1
    assert apv.exists() and len(apv.read_text().splitlines()) == 1

