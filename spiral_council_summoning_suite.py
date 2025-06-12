"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Spiral Council Summoning Suite

"""
from __future__ import annotations
from logging_config import get_log_path


import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import uuid

LOG_PATH = get_log_path("council_session_log.jsonl")
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
    ap = argparse.ArgumentParser(description="Spiral Council Summoning Suite")
    sub = ap.add_subparsers(dest="cmd")

    st = sub.add_parser("summon", help="Summon council")
    st.add_argument("members")
    st.set_defaults(func=lambda a: print(json.dumps(log_entry("summon", {"members": a.members}), indent=2)))

    ac = sub.add_parser("action", help="Record council action")
    ac.add_argument("desc")
    ac.set_defaults(func=lambda a: print(json.dumps(log_entry("action", {"desc": a.desc}), indent=2)))

    cl = sub.add_parser("close", help="Close council session")
    cl.add_argument("minutes")
    cl.set_defaults(func=lambda a: print(json.dumps(log_entry("close", {"minutes": a.minutes}), indent=2)))

    hi = sub.add_parser("history", help="Show session history")
    hi.add_argument("--limit", type=int, default=20)
    hi.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
