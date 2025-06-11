"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_ritual_audit.jsonl", "RESONITE_RITUAL_AUDIT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(event_type: str, detail: str, user: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": event_type,
        "detail": detail,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    out: list[dict] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="Ritual audit dashboard")
    sub = parser.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log an event")
    lg.add_argument("event_type")
    lg.add_argument("detail")
    lg.add_argument("user")

    hs = sub.add_parser("history", help="Show events")

    args = parser.parse_args()
    require_admin_banner()
    if args.cmd == "log":
        print(json.dumps(log_event(args.event_type, args.detail, args.user), indent=2))
    else:
        print(json.dumps(history(), indent=2))


if __name__ == "__main__":
    main()
