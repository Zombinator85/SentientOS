from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("spiral_ritual_law.jsonl", "SPIRAL_RITUAL_LAW_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_entry(user: str, action: str, text: str = "") -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "action": action,
        "text": text,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_laws() -> list[dict]:
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
    parser = argparse.ArgumentParser(description="Ritual law compiler")
    sub = parser.add_subparsers(dest="cmd")

    add_p = sub.add_parser("add", help="Add a new ritual law")
    add_p.add_argument("user")
    add_p.add_argument("text")

    export_p = sub.add_parser("export", help="Export compiled law")

    list_p = sub.add_parser("list", help="List laws")

    args = parser.parse_args()
    require_admin_banner()
    if args.cmd == "add":
        print(json.dumps(log_entry(args.user, "add", args.text), indent=2))
    elif args.cmd == "export":
        print(json.dumps(list_laws(), indent=2))
    else:
        print(json.dumps(list_laws(), indent=2))


if __name__ == "__main__":
    main()
