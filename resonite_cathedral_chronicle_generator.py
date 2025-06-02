from __future__ import annotations

"""Resonite Cathedral Chronicle Generator

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""

from admin_utils import require_admin_banner

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path("logs/resonite_cathedral_chronicle_generator.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_entry(description: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "description": description}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_entry(data.get("description", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Cathedral Chronicle Generator")
    sub = ap.add_subparsers(dest="cmd")

    rec = sub.add_parser("record", help="Record chronicle entry")
    rec.add_argument("description")
    rec.set_defaults(func=lambda a: print(json.dumps(log_entry(a.description), indent=2)))

    view = sub.add_parser("history", help="Show history")
    view.add_argument("--limit", type=int, default=20)
    view.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
