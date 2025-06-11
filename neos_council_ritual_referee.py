"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval



import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_ritual_referee.jsonl", "NEOS_RITUAL_REFEREE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_intervention(issue: str, note: str = "") -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "issue": issue, "note": note}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Autonomous Council Ritual Referee")
    sub = ap.add_subparsers(dest="cmd")

    iv = sub.add_parser("intervene", help="Log a ceremony intervention")
    iv.add_argument("issue")
    iv.add_argument("--note", default="")
    iv.set_defaults(func=lambda a: print(json.dumps(log_intervention(a.issue, a.note), indent=2)))

    hist = sub.add_parser("history", help="Show intervention history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
