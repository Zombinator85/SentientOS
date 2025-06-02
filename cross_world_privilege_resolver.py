"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

CONFLICT_LOG = Path(os.getenv("PRIVILEGE_CONFLICT_LOG", "logs/privilege_conflict.jsonl"))
CONFLICT_LOG.parent.mkdir(parents=True, exist_ok=True)


def log_conflict(world: str, detail: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "world": world,
        "detail": detail,
    }
    with CONFLICT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history() -> List[Dict[str, str]]:
    if not CONFLICT_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in CONFLICT_LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Cross-World Privilege Drift/Conflict Resolver")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log a conflict")
    lg.add_argument("world")
    lg.add_argument("detail")
    lg.set_defaults(func=lambda a: print(json.dumps(log_conflict(a.world, a.detail), indent=2)))

    ls = sub.add_parser("history", help="Show conflicts")
    ls.set_defaults(func=lambda a: print(json.dumps(history(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
