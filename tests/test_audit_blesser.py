"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import audit_blesser

class DummyCP:
    stdout = "prev hash mismatch"
    stderr = ""


def test_auto_approve(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    bless_file = tmp_path / "SANCTUARY_BLESSINGS.jsonl"
    monkeypatch.setattr(audit_blesser, "BLESSINGS_FILE", bless_file)
    monkeypatch.setattr(audit_blesser, "run_verify", lambda: DummyCP())
    ret = audit_blesser.main([])
    assert ret == 0
    assert bless_file.exists()
    data = json.loads(bless_file.read_text().splitlines()[-1])
    assert data["action"] == "automatic audit blessing"


def test_no_bless(monkeypatch):
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "")
    monkeypatch.setattr(audit_blesser, "run_verify", lambda: DummyCP())
    monkeypatch.setattr(audit_blesser, "append_blessing", lambda: None)
    monkeypatch.setattr(audit_blesser, "prompt_yes_no", lambda p: False)
    ret = audit_blesser.main([])
    assert ret == 1

