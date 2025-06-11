"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
from pathlib import Path

BLESSING_LEDGER = get_log_path("blessing_ledger.jsonl")


def check_integrity() -> bool:
    if not BLESSING_LEDGER.exists():
        print("Ledger empty")
        return True
    seen = set()
    for line in BLESSING_LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except Exception:
            print("Corrupt entry detected")
            return False
        ts = entry.get("timestamp")
        if ts in seen:
            print("Duplicate timestamp", ts)
            return False
        seen.add(ts)
    print("ledger blessed")
    return True


if __name__ == "__main__":
    check_integrity()
