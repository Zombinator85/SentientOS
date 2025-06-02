from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List

import presence_ledger as pl

LOG_PATH = Path(
    os.getenv("NEOS_FEDERATION_PRESENCE_EXPORT_LOG", "logs/neos_federation_presence_export.jsonl")
)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def export_ledger(out_path: str) -> str:
    src = pl.LEDGER_PATH
    dest = Path(out_path)
    if src.exists():
        dest.write_text(src.read_text(encoding="utf-8"))
    else:
        dest.write_text("")
    entry = {"timestamp": datetime.utcnow().isoformat(), "export": str(dest)}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return str(dest)


def export_history(limit: int = 20) -> List[dict]:
    if not LOG_PATH.exists():
        return []
    out: List[dict] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(
        description="NeosVR Federation Presence Ledger Exporter"
    )
    sub = ap.add_subparsers(dest="cmd")

    ex = sub.add_parser("export", help="Export presence ledger")
    ex.add_argument("path")
    ex.set_defaults(func=lambda a: print(json.dumps(export_ledger(a.path), indent=2)))

    hist = sub.add_parser("history", help="Show export history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(export_history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
