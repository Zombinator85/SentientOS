from __future__ import annotations
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_ritual_compliance.jsonl", "NEOS_RITUAL_COMPLIANCE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_check(component: str, status: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "component": component,
        "status": status,
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
    ap = argparse.ArgumentParser(description="NeosVR Ritual Compliance Dashboard")
    sub = ap.add_subparsers(dest="cmd")

    chk = sub.add_parser("check", help="Log compliance check")
    chk.add_argument("component")
    chk.add_argument("status")
    chk.set_defaults(func=lambda a: print(json.dumps(log_check(a.component, a.status), indent=2)))

    hist = sub.add_parser("history", help="Show check history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
