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


def record_action(action: str, councilor: str) -> Dict[str, str]:
    """Record an onboarding or succession action."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "councilor": councilor,
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
    ap = argparse.ArgumentParser(description="NeosVR Council Succession Ceremony")
    sub = ap.add_subparsers(dest="cmd")

    ob = sub.add_parser("onboard", help="Onboard councilor")
    ob.add_argument("name")
    ob.set_defaults(func=lambda a: print(json.dumps(record_action("onboard", a.name), indent=2)))

    bless = sub.add_parser("bless", help="Bless councilor")
    bless.add_argument("name")
    bless.set_defaults(func=lambda a: print(json.dumps(record_action("bless", a.name), indent=2)))

    hist = sub.add_parser("history", help="Show ceremony history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
