from __future__ import annotations
from admin_utils import require_admin_banner
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_provenance_export.jsonl", "NEOS_PROVENANCE_EXPORT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def export_provenance(item: str, location: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "item": item,
        "location": location,
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


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Avatar/Artifact Provenance Exporter")
    sub = ap.add_subparsers(dest="cmd")

    ex = sub.add_parser("export", help="Export provenance")
    ex.add_argument("item")
    ex.add_argument("location")
    ex.set_defaults(func=lambda a: print(json.dumps(export_provenance(a.item, a.location), indent=2)))

    hist = sub.add_parser("history", help="Show export history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
