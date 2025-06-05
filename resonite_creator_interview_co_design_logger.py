from admin_utils import require_admin_banner, require_lumos_approval
"""Resonite Creator Interview/Co-Design Logger

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path


import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import uuid

LOG_PATH = get_log_path("creator_interview_log.jsonl")
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
    ap = argparse.ArgumentParser(description="Resonite Creator Interview/Co-Design Logger")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log interview")
    lg.add_argument("participants")
    lg.add_argument("notes")
    lg.set_defaults(func=lambda a: print(json.dumps(log_entry("log", {"participants": a.participants, "notes": a.notes}), indent=2)))

    hi = sub.add_parser("history", help="Show interview history")
    hi.add_argument("--limit", type=int, default=20)
    hi.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
