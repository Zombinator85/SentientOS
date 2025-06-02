"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from logging_config import get_log_path
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

FEEDBACK_LOG = get_log_path("teaching_feedback.jsonl", "TEACHING_FEEDBACK_LOG")
FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)


def record_feedback(user: str, comment: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "comment": comment,
    }
    with FEEDBACK_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(user: str = "") -> List[Dict[str, str]]:
    if not FEEDBACK_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in FEEDBACK_LOG.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if user and obj.get("user") != user:
            continue
        out.append(obj)
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Teaching Reflection Feedback Loop")
    sub = ap.add_subparsers(dest="cmd")

    rec = sub.add_parser("record", help="Record feedback")
    rec.add_argument("user")
    rec.add_argument("comment")
    rec.set_defaults(func=lambda a: print(json.dumps(record_feedback(a.user, a.comment), indent=2)))

    ls = sub.add_parser("history", help="Show feedback history")
    ls.add_argument("--user", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(history(a.user), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
