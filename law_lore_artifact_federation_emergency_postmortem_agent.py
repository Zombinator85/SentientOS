from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Law/Lore/Artifact/Federation Emergency Postmortem Agent
Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("postmortem.jsonl", "POSTMORTEM_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def trigger(event: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event, "action": "triggered"}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def record(decision: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "decision": decision}
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
    ap = argparse.ArgumentParser(description="Emergency Postmortem Agent")
    sub = ap.add_subparsers(dest="cmd")

    tg = sub.add_parser("trigger", help="Trigger postmortem")
    tg.add_argument("event")
    tg.set_defaults(func=lambda a: print(json.dumps(trigger(a.event), indent=2)))

    rc = sub.add_parser("record", help="Record council decision")
    rc.add_argument("decision")
    rc.set_defaults(func=lambda a: print(json.dumps(record(a.decision), indent=2)))

    hs = sub.add_parser("history", help="Show postmortem history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
