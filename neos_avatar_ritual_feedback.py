from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_avatar_ritual_feedback.jsonl", "NEOS_RITUAL_FEEDBACK_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_feedback(avatar: str, feedback: str, adaptation: str = "") -> Dict[str, str]:
    """Record ritual feedback from VR."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "feedback": feedback,
        "adaptation": adaptation,
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


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Avatar Ritual Feedback Loop")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Record feedback")
    lg.add_argument("avatar")
    lg.add_argument("feedback")
    lg.add_argument("--adaptation", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_feedback(a.avatar, a.feedback, a.adaptation), indent=2)))

    hist = sub.add_parser("history", help="Show feedback history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
