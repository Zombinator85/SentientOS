"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
import json
import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import memory_manager as mm
import notification
import presence_analytics as pa


def create_entry(ts: str, emotions: dict | None = None, tags=None, text=""):
    eid = mm.append_memory(text or json.dumps({}), emotions=emotions or {}, tags=tags or [])
    fp = mm.RAW_PATH / f"{eid}.json"
    data = json.loads(fp.read_text())
    data["timestamp"] = ts
    fp.write_text(json.dumps(data))
    return eid


def test_basic_analytics(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload
    reload(mm)
    reload(notification)
    reload(pa)

    # create emotion entries
    create_entry("2023-01-02T09:00:00", {"Joy": 0.8})
    create_entry("2023-01-02T10:00:00", {"Sadness": 0.9})

    # create action success and failure
    create_entry("2023-01-02T11:00:00", tags=["act"], text=json.dumps({"status": "finished"}))
    create_entry("2023-01-02T12:00:00", tags=["act"], text=json.dumps({"status": "failed", "error": "oops"}))

    # patch events
    notification.send("patch_approved", {})
    notification.send("patch_rejected", {})

    data = pa.analytics()
    assert data["action_stats"]["total"] == 2
    assert data["patch_stats"]["patch_approved"] == 1
    trends = data["emotion_trends"]
    assert "Monday" in next(iter(trends.values()))

    suggestions = pa.suggest_improvements(data)
    assert any("sadness" in s.lower() for s in suggestions)
