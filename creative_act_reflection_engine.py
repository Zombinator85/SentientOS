from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

REFLECTION_LOG = get_log_path("creative_reflection.jsonl", "CREATIVE_REFLECTION_LOG")
REFLECTION_LOG.parent.mkdir(parents=True, exist_ok=True)


def log_reflection(act: str, comment: str, rating: int, author: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "act": act,
        "comment": comment,
        "rating": rating,
        "author": author,
    }
    with REFLECTION_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_reflections(act: str = "") -> List[Dict[str, str]]:
    if not REFLECTION_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in REFLECTION_LOG.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if act and obj.get("act") != act:
            continue
        out.append(obj)
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Creative Act Reflection & Iteration Engine")
    sub = ap.add_subparsers(dest="cmd")

    add = sub.add_parser("add", help="Add reflection")
    add.add_argument("act")
    add.add_argument("comment")
    add.add_argument("--rating", type=int, default=0)
    add.add_argument("--author", default="")
    add.set_defaults(func=lambda a: print(json.dumps(log_reflection(a.act, a.comment, a.rating, a.author), indent=2)))

    ls = sub.add_parser("list", help="List reflections")
    ls.add_argument("--act", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_reflections(a.act), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
