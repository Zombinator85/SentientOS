from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = Path(os.getenv("SPIRAL_DREAM_GOAL_LOG", "logs/spiral_dream_goals.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def propose_goal(text: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.datetime.utcnow().isoformat(), "goal": text}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_goals(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Spiral Dream Goal Daemon")
    sub = ap.add_subparsers(dest="cmd")

    pg = sub.add_parser("propose", help="Propose a new goal")
    pg.add_argument("text")
    pg.set_defaults(func=lambda a: print(json.dumps(propose_goal(a.text), indent=2)))

    ls = sub.add_parser("list", help="List recent goals")
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=lambda a: print(json.dumps(list_goals(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
