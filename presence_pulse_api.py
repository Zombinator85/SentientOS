from logging_config import get_log_path
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
CONFESSIONAL_LOG = get_log_path("confessional_log.jsonl", "CONFESSIONAL_LOG")
SUPPORT_LOG = get_log_path("support_log.jsonl")
HERESY_LOG = get_log_path("heresy_log.jsonl", "HERESY_LOG")
FORGIVENESS_LOG = get_log_path("forgiveness_ledger.jsonl", "FORGIVENESS_LEDGER")


def _load(path: Path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def pulse(minutes: int = 60) -> float:
    now = datetime.utcnow()
    start = now - timedelta(minutes=minutes)
    count = 0
    for path in [CONFESSIONAL_LOG, SUPPORT_LOG, HERESY_LOG, FORGIVENESS_LOG]:
        for e in _load(path):
            ts = e.get("timestamp")
            try:
                dt = datetime.fromisoformat(str(ts))
            except Exception:
                continue
            if dt >= start:
                count += 1
    return count / float(minutes)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Presence pulse")
    p.add_argument("--minutes", type=int, default=60)
    args = p.parse_args()
    print(json.dumps({"pulse": pulse(args.minutes)}))
