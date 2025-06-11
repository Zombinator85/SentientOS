"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import time
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ocr_log_export as oe


def test_export_last_day_csv(tmp_path):
    log = tmp_path / "ocr.jsonl"
    now = time.time()
    lines = [
        json.dumps({"timestamp": now - 90000, "message": "old", "reply": "", "count": 1}),
        json.dumps({"timestamp": now, "message": "new", "reply": "hi", "count": 2}),
    ]
    log.write_text("\n".join(lines))
    out = oe.export_last_day_csv(log)
    assert out
    csv = Path(out).read_text()
    assert "new" in csv and "old" not in csv

