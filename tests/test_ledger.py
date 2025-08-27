from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import hashlib
from pathlib import Path

from wdm.runner import run_wdm


def test_emotion_pump_ledger(tmp_path):
    ledger = Path("logs/migration_ledger.jsonl")
    if ledger.exists():
        ledger.unlink()

    cfg = {
        "logging": {
            "jsonl_path": str(tmp_path / "wdm"),
            "summary_path": str(tmp_path / "summaries.jsonl"),
            "presence_path": str(tmp_path / "presence.jsonl"),
        }
    }

    run_wdm("hi", {"incoming_request": True}, cfg)

    lines = ledger.read_text().splitlines()
    assert lines, "ledger should have at least one entry"
    entry = json.loads(lines[-1])
    assert entry["type"] == "presence"

    presence_line = Path(cfg["logging"]["presence_path"]).read_text().splitlines()[-1]
    expected = "sha256:" + hashlib.sha256(presence_line.encode("utf-8")).hexdigest()
    assert entry["checksum"] == expected

