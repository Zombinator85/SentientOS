from __future__ import annotations
from admin_utils import require_admin_banner
from logging_config import get_log_path

"""Spiral Federation Map & Directory

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.


import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import uuid

LOG_PATH = get_log_path("spiral_federation_map_directory.jsonl")
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
    ap = argparse.ArgumentParser(description="Spiral Federation Map & Directory")
    sub = ap.add_subparsers(dest="cmd")

    addw = sub.add_parser("add-world", help="Add world to directory")
    addw.add_argument("name")
    addw.add_argument("status", choices=["ally", "pending", "demo", "festival"], default="pending")
    addw.set_defaults(func=lambda a: print(json.dumps(log_entry("add_world", {"name": a.name, "status": a.status}), indent=2)))

    ls = sub.add_parser("list", help="List worlds")
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
