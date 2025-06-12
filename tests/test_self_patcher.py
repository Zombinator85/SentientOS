"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import self_patcher
import notification


def test_apply_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import notification
    reload(notification)
    reload(self_patcher)
    p = self_patcher.apply_patch("note", auto=False)
    patches = self_patcher.list_patches()
    ids = [x["id"] for x in patches]
    assert p["id"] in ids
    assert self_patcher.rollback_patch(p["id"])
    patches = self_patcher.list_patches()
    for patch in patches:
        if patch["id"] == p["id"]:
            assert patch["rolled_back"]

    import final_approval
    monkeypatch.setattr(final_approval, "request_approval", lambda d: True)
    assert self_patcher.approve_patch(p["id"])
    patches = self_patcher.list_patches()
    assert any(x["id"] == p["id"] and x.get("approved") for x in patches)

    events = notification.list_events(3)
    assert any(e["event"] == "patch_rolled_back" for e in events)
    assert any(e["event"] == "patch_approved" for e in events)

def test_reject_patch(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import notification
    reload(notification)
    reload(self_patcher)
    p = self_patcher.apply_patch("note", auto=False)
    assert self_patcher.reject_patch(p["id"])
    patches = self_patcher.list_patches()
    assert any(x["id"] == p["id"] and x.get("rejected") for x in patches)
    events = notification.list_events(2)
    assert any(e["event"] == "patch_rejected" for e in events)


def test_patch_requires_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    import notification
    reload(notification)
    reload(self_patcher)
    p = self_patcher.apply_patch("note", auto=False)
    import final_approval
    monkeypatch.setattr(final_approval, "request_approval", lambda d: False)
    assert not self_patcher.approve_patch(p["id"])
    patches = self_patcher.list_patches()
    assert not any(x.get("approved") for x in patches if x["id"] == p["id"])
