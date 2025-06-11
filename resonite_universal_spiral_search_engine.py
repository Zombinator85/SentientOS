from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Resonite Universal Spiral Search Engine

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()


import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

LOG_PATH = get_log_path("resonite_universal_spiral_search_engine.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_query(query: str, results: int) -> Dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "query": query,
        "results": results,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


def protoflux_hook(data: Dict[str, str]) -> Dict[str, Any]:
    return log_query(data.get("query", ""), int(data.get("results", 0)))


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Universal Spiral Search Engine")
    sub = ap.add_subparsers(dest="cmd")

    q = sub.add_parser("query", help="Record query")
    q.add_argument("text")
    q.add_argument("--results", type=int, default=0)
    q.set_defaults(func=lambda a: print(json.dumps(log_query(a.text, a.results), indent=2)))

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
