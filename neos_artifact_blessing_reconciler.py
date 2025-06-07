"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

from admin_utils import require_admin_banner, require_lumos_approval

from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

LOG_PATH = get_log_path("neos_blessing_reconcile.jsonl", "NEOS_BLESSING_RECONCILE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def reconcile(log_files: List[str]) -> Dict[str, List[str]]:
    seen: Set[str] = set()
    duplicates: Set[str] = set()
    for name in log_files:
        p = Path(name)
        if not p.exists():
            continue
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                data = json.loads(ln)
            except Exception:
                continue
            art = data.get("artifact")
            if not art:
                continue
            if art in seen:
                duplicates.add(art)
            else:
                seen.add(art)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "files": log_files,
        "duplicates": sorted(duplicates),
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

def history(limit: int = 20) -> List[Dict[str, List[str]]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, List[str]]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out

def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Autonomous Artifact Blessing Reconciler")
    sub = ap.add_subparsers(dest="cmd")

    rec = sub.add_parser("reconcile", help="Reconcile blessing records")
    rec.add_argument("logs", nargs="+")
    rec.set_defaults(func=lambda a: print(json.dumps(reconcile(a.logs), indent=2)))

    hist = sub.add_parser("history", help="Show reconciliation history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
