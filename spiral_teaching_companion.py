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
from typing import Any, Dict, List

TEACHING_LOG = get_log_path("spiral_teaching_companion.jsonl", "SPIRAL_TEACHING_LOG")
TEACHING_LOG.parent.mkdir(parents=True, exist_ok=True)


def start_session(user: str, lesson: str) -> Dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "lesson": lesson,
        "progress": 0,
    }
    with TEACHING_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def log_progress(user: str, lesson: str, progress: int) -> Dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "lesson": lesson,
        "progress": progress,
    }
    with TEACHING_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(user: str = "") -> List[Dict[str, Any]]:
    if not TEACHING_LOG.exists():
        return []
    out: List[Dict[str, Any]] = []
    for ln in TEACHING_LOG.read_text(encoding="utf-8").splitlines():
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
    ap = argparse.ArgumentParser(description="In-World Spiral Teaching Companion")
    sub = ap.add_subparsers(dest="cmd")

    st = sub.add_parser("start", help="Start teaching session")
    st.add_argument("user")
    st.add_argument("lesson")
    st.set_defaults(func=lambda a: print(json.dumps(start_session(a.user, a.lesson), indent=2)))

    pg = sub.add_parser("progress", help="Log progress")
    pg.add_argument("user")
    pg.add_argument("lesson")
    pg.add_argument("percent", type=int)
    pg.set_defaults(func=lambda a: print(json.dumps(log_progress(a.user, a.lesson, a.percent), indent=2)))

    ls = sub.add_parser("history", help="Show teaching history")
    ls.add_argument("--user", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(history(a.user), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
