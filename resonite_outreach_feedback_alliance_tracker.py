"""Resonite Outreach Feedback & Alliance Tracker

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from __future__ import annotations

from admin_utils import require_admin_banner

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import uuid

LOG_PATH = Path("logs/outreach_feedback_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_entry(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        **data,
    }
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


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Outreach Feedback & Alliance Tracker")
    sub = ap.add_subparsers(dest="cmd")

    rc = sub.add_parser("record", help="Record feedback")
    rc.add_argument("source")
    rc.add_argument("message")
    rc.add_argument("--status", default="awaiting reply")
    rc.set_defaults(func=lambda a: print(json.dumps(log_entry("record", {"source": a.source, "message": a.message, "status": a.status}), indent=2)))

    st = sub.add_parser("status", help="Show feedback history")
    st.add_argument("--limit", type=int, default=20)
    st.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
