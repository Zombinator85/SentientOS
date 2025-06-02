from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("NEOS_LIVING_LAW_DASHBOARD_LOG", "logs/neos_living_law_dashboard.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def record_action(user: str, action: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "action": action,
        "note": note,
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


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Living Law Dashboard UX")
    sub = ap.add_subparsers(dest="cmd")

    rec = sub.add_parser("record", help="Record dashboard action")
    rec.add_argument("user")
    rec.add_argument("action")
    rec.add_argument("--note", default="")
    rec.set_defaults(func=lambda a: print(json.dumps(record_action(a.user, a.action, a.note), indent=2)))

    hist = sub.add_parser("history", help="Show action history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
