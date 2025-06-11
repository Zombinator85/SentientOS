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

import ocr_log_html_report as rep


def test_generate_html_report(tmp_path):
    log = tmp_path / "ocr.jsonl"
    data = [
        {"timestamp": 1, "message": "hi", "count": 2},
        {"timestamp": 2, "message": "hi", "count": 1},
        {"timestamp": 3, "message": "bye", "count": 1},
    ]
    log.write_text("\n".join(json.dumps(d) for d in data))
    out = rep.generate_html_report(log)
    assert out
    html = Path(out).read_text()
    assert "<table" in html and "hi" in html and "bye" in html
