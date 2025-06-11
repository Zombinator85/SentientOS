from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatars with Council/Oracle Delegation."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_delegation.jsonl", "AVATAR_DELEGATION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def delegate(avatar: str, role: str, duration: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "role": role,
        "duration": duration,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_delegations() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Council/Oracle Delegation")
    sub = ap.add_subparsers(dest="cmd")

    dl = sub.add_parser("delegate", help="Delegate a role to an avatar")
    dl.add_argument("avatar")
    dl.add_argument("role")
    dl.add_argument("duration")
    dl.set_defaults(func=lambda a: print(json.dumps(delegate(a.avatar, a.role, a.duration), indent=2)))

    ls = sub.add_parser("list", help="List delegations")
    ls.set_defaults(func=lambda a: print(json.dumps(list_delegations(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
