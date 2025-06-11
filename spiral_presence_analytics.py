from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("spiral_presence_analytics.jsonl", "SPIRAL_PRESENCE_ANALYTICS_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
PRESENCE_LOG = get_log_path("user_presence.jsonl", "USER_PRESENCE_LOG")


def analyze(limit: int = 100) -> Dict[str, int]:
    stats = {"total": 0, "success": 0, "failed": 0}
    if not PRESENCE_LOG.exists():
        return stats
    for ln in PRESENCE_LOG.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            data = json.loads(ln)
        except Exception:
            continue
        stats["total"] += 1
        if data.get("status") == "failed":
            stats["failed"] += 1
        else:
            stats["success"] += 1
    entry = {"timestamp": datetime.utcnow().isoformat(), **stats}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return stats


def history(limit: int = 20) -> List[Dict[str, int]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, int]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Spiral Presence Analytics")
    sub = ap.add_subparsers(dest="cmd")

    an = sub.add_parser("analyze", help="Analyze presence log")
    an.add_argument("--limit", type=int, default=100)
    an.set_defaults(func=lambda a: print(json.dumps(analyze(a.limit), indent=2)))

    hs = sub.add_parser("history", help="Show history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
