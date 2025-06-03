from admin_utils import require_admin_banner
"""Spiral Manifesto Publisher

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
from __future__ import annotations
from logging_config import get_log_path


import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import uuid

LOG_PATH = get_log_path("manifesto_circulation_log.jsonl")
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
    ap = argparse.ArgumentParser(description="Spiral Manifesto Publisher")
    sub = ap.add_subparsers(dest="cmd")

    pb = sub.add_parser("publish", help="Publish manifesto")
    pb.add_argument("manifesto")
    pb.set_defaults(func=lambda a: print(json.dumps(log_entry("publish", {"manifesto": a.manifesto}), indent=2)))

    rd = sub.add_parser("read", help="Log a read of the manifesto")
    rd.add_argument("user")
    rd.set_defaults(func=lambda a: print(json.dumps(log_entry("read", {"user": a.user}), indent=2)))

    en = sub.add_parser("endorse", help="Record endorsement")
    en.add_argument("user")
    en.set_defaults(func=lambda a: print(json.dumps(log_entry("endorse", {"user": a.user}), indent=2)))

    hi = sub.add_parser("history", help="Show circulation history")
    hi.add_argument("--limit", type=int, default=20)
    hi.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
