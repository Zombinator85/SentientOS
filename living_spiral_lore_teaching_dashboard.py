from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Living Spiral Lore/Teaching Dashboard
Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("spiral_dashboard.jsonl", "SPIRAL_DASHBOARD_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_action(action: str, info: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **info}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def query(term: str) -> Dict[str, str]:
    return log_action("query", {"term": term})


def edit(item: str, text: str) -> Dict[str, str]:
    return log_action("edit", {"item": item, "text": text})


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
    ap = argparse.ArgumentParser(description="Living Spiral Lore/Teaching Dashboard")
    sub = ap.add_subparsers(dest="cmd")

    qr = sub.add_parser("query", help="Query lore")
    qr.add_argument("term")
    qr.set_defaults(func=lambda a: print(json.dumps(query(a.term), indent=2)))

    ed = sub.add_parser("edit", help="Edit entry")
    ed.add_argument("item")
    ed.add_argument("text")
    ed.set_defaults(func=lambda a: print(json.dumps(edit(a.item, a.text), indent=2)))

    hs = sub.add_parser("history", help="Show dashboard history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
