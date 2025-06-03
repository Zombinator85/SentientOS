from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

LOG_PATH = get_log_path("resonite_privilege_ring.jsonl", "RESONITE_PRIVILEGE_RING_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_transition(user: str, ring: str, action: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "ring": ring,
        "action": action,
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
    parser = argparse.ArgumentParser(description="Privilege ring orchestrator")
    sub = parser.add_subparsers(dest="cmd")

    st = sub.add_parser("set", help="Set user ring")
    st.add_argument("user")
    st.add_argument("ring")

    hs = sub.add_parser("history", help="Show ring transitions")

    args = parser.parse_args()
    require_admin_banner()
    if args.cmd == "set":
        print(json.dumps(log_transition(args.user, args.ring, "set"), indent=2))
    else:
        print(json.dumps(history(), indent=2))


if __name__ == "__main__":
    main()
