import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import self_patcher


def test_apply_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
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

    assert self_patcher.approve_patch(p["id"])
    patches = self_patcher.list_patches()
    assert any(x["id"] == p["id"] and x.get("approved") for x in patches)


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
