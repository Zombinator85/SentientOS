from __future__ import annotations
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_compliance_feedback.jsonl", "NEOS_COMPLIANCE_FEEDBACK_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def submit_feedback(user: str, feedback: str, category: str = "general") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "category": category,
        "feedback": feedback,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

def stats() -> Dict[str, int]:
    count: Counter[str] = Counter()
    if not LOG_PATH.exists():
        return {}
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            data = json.loads(ln)
            count[data.get("category", "general")] += 1
        except Exception:
            continue
    return dict(count)

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
    ap = argparse.ArgumentParser(description="NeosVR Autonomous Compliance Feedback Engine")
    sub = ap.add_subparsers(dest="cmd")

    subm = sub.add_parser("submit", help="Submit feedback")
    subm.add_argument("user")
    subm.add_argument("feedback")
    subm.add_argument("--category", default="general")
    subm.set_defaults(func=lambda a: print(json.dumps(submit_feedback(a.user, a.feedback, a.category), indent=2)))

    st = sub.add_parser("stats", help="Show feedback statistics")
    st.set_defaults(func=lambda a: print(json.dumps(stats(), indent=2)))

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
