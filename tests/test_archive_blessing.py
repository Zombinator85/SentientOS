import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import audit_immutability as ai


def test_seal_log(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_BLESSING_LOG", str(tmp_path / "blessing.jsonl"))
    monkeypatch.setenv("ARCHIVE_DIR", str(tmp_path / "arch"))
    import archive_blessing as ab
    importlib.reload(ab)
    log = tmp_path / "log.jsonl"
    ai.append_entry(log, {"a": 1})
    entry = ab.seal_log(log, "council")
    assert Path(entry["archive"]).exists()
    assert entry["verified"] is True
    hist = ab.history()
    assert hist and hist[-1]["curator"] == "council"
