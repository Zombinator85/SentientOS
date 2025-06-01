import os
import sys
from importlib import reload
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl


def test_audit_use(tmp_path, monkeypatch):
    log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("PRIVILEGED_AUDIT_FILE", str(log))
    reload(pl)
    pl.audit_use("cli", "tool")
    data = log.read_text().strip()
    assert "tool" in data
