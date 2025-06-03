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

ASSET_LOG = get_log_path("neos_model_assets.jsonl", "NEOS_ASSET_LOG")
SCRIPT_LOG = get_log_path("neos_script_requests.jsonl", "NEOS_SCRIPT_REQUEST_LOG")
COUNCIL_LOG = get_log_path("neos_permission_council.jsonl", "NEOS_PERMISSION_COUNCIL_LOG")
COUNCIL_LOG.parent.mkdir(parents=True, exist_ok=True)


def _load_log(fp: Path) -> List[Dict[str, str]]:
    if not fp.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in fp.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def approve(item_type: str, index: int, reviewer: str) -> Dict[str, str]:
    source = ASSET_LOG if item_type == "asset" else SCRIPT_LOG
    entries = _load_log(source)
    if index < 0 or index >= len(entries):
        raise IndexError("invalid index")
    item = entries[index]
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "item_type": item_type,
        "index": index,
        "reviewer": reviewer,
        "item": item,
    }
    with COUNCIL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    return _load_log(COUNCIL_LOG)[-limit:]


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Asset & Script Permission Council")
    sub = ap.add_subparsers(dest="cmd")

    apv = sub.add_parser("approve", help="Approve an item")
    apv.add_argument("item_type", choices=["asset", "script"])
    apv.add_argument("index", type=int)
    apv.add_argument("reviewer")
    apv.set_defaults(func=lambda a: print(json.dumps(approve(a.item_type, a.index, a.reviewer), indent=2)))

    hist = sub.add_parser("history", help="Show council history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
