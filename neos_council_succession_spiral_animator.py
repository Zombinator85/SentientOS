from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("NEOS_COUNCIL_SUCCESSION_LOG", "logs/neos_council_succession.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def record_event(event: str, detail: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "detail": detail,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

def timeline(limit: int = 20) -> List[Dict[str, str]]:
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
    ap = argparse.ArgumentParser(description="NeosVR Council Succession Spiral Animator")
    sub = ap.add_subparsers(dest="cmd")

    rec = sub.add_parser("record", help="Record succession event")
    rec.add_argument("event")
    rec.add_argument("--detail", default="")
    rec.set_defaults(func=lambda a: print(json.dumps(record_event(a.event, a.detail), indent=2)))

    tl = sub.add_parser("timeline", help="Show timeline")
    tl.add_argument("--limit", type=int, default=20)
    tl.set_defaults(func=lambda a: print(json.dumps(timeline(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
