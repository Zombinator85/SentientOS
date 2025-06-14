"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
"""CLI helper for the blessing ledger."""

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Dict, List

from logging_config import get_log_path
from log_utils import append_json

LEDGER_PATH = Path("docs/BLESSING_LEDGER.jsonl")
LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_blessing(module: str, ritual: str, blessed_by: str) -> Dict[str, str]:
    entry = {
        "module": module,
        "blessed_at": dt.datetime.utcnow().isoformat() + "Z",
        "ritual": ritual,
        "blessed_by": blessed_by,
    }
    append_json(LEDGER_PATH, entry)
    return entry


def view_ledger(limit: int = 5) -> List[Dict[str, str]]:
    if not LEDGER_PATH.exists():
        return []
    lines = LEDGER_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Blessing ledger utility")
    ap.add_argument("module", nargs="?")
    ap.add_argument("--ritual", default="module initialized")
    ap.add_argument("--blessed-by", default="bootstrap_cathedral")
    ap.add_argument("--view", action="store_true")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()
    if args.view:
        print(json.dumps(view_ledger(args.limit), indent=2))
        return
    if not args.module:
        ap.print_help()
        return
    entry = log_blessing(args.module, args.ritual, args.blessed_by)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
