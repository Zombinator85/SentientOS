from __future__ import annotations

"""Resonite Ritual Evidence Exporter

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""

from admin_utils import require_admin_banner

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path("logs/resonite_ritual_evidence_exporter.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_export(item: str, path: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "item": item,
        "path": path,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_export(data.get("item", "unknown"), data.get("path", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Ritual Evidence Exporter")
    sub = ap.add_subparsers(dest="cmd")

    ex = sub.add_parser("export", help="Log export")
    ex.add_argument("item")
    ex.add_argument("path")
    ex.set_defaults(func=lambda a: print(json.dumps(log_export(a.item, a.path), indent=2)))

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
