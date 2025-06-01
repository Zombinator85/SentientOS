import json
import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import presence_ledger as pl

def test_recent_privilege_attempts(tmp_path, monkeypatch):
    path = tmp_path / "user_presence.jsonl"
    monkeypatch.setenv("USER_PRESENCE_LOG", str(path))
    entries = [
        {"timestamp": "t1", "event": "admin_privilege_check", "status": "success"},
        {"timestamp": "t2", "event": "admin_privilege_check", "status": "failed"},
        {"timestamp": "t3", "event": "something_else"},
    ]
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    import importlib
    importlib.reload(pl)
    recent = pl.recent_privilege_attempts()
    assert len(recent) == 2
    assert recent[0]["timestamp"] == "t1"
    assert recent[1]["status"] == "failed"
