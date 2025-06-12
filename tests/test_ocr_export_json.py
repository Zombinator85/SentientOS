"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import json
import time
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ocr_log_export as oe


def test_export_last_day_json(tmp_path):
    log = tmp_path / "ocr.jsonl"
    now = time.time()
    lines = [
        json.dumps({"timestamp": now - 90000, "message": "old", "count": 1}),
        json.dumps({"timestamp": now, "message": "new", "count": 2}),
        json.dumps({"timestamp": now+1, "message": "new", "count": 1}),
    ]
    log.write_text("\n".join(lines))
    out = oe.export_last_day_json(log)
    assert out
    data = json.loads(Path(out).read_text())
    assert data[0]["message"] == "new"
    assert len(data[0]["timestamps"]) == 2
