from admin_utils import require_admin_banner, require_lumos_approval
"""Council Member Onboarding & Quorum Ritual

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


CONFIG_PATH = Path(os.getenv("COUNCIL_CONFIG", "config/council.json"))
LOG_PATH = get_log_path("council_onboarding.jsonl", "COUNCIL_ONBOARDING_LOG")
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_members() -> List[Dict[str, Any]]:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return []


def save_members(members: List[Dict[str, Any]]) -> None:
    CONFIG_PATH.write_text(json.dumps(members, indent=2))


def quorum_count(members: List[Dict[str, Any]]) -> int:
    return max(1, len(members) // 2 + 1)


def onboard(name: str, key: str, role: str, approvers: List[str]) -> Dict[str, Any]:
    members = load_members()
    required = quorum_count(members)
    if len(approvers) < required:
        raise SystemExit(f"Quorum not met: need {required} approvals")
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "key": key,
        "role": role,
        "approvers": approvers,
    }
    members.append({"name": name, "key": key, "role": role})
    save_members(members)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def cli() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Council onboarding")
    sub = ap.add_subparsers(dest="cmd")
    add = sub.add_parser("add", help="Onboard member")
    add.add_argument("name")
    add.add_argument("key")
    add.add_argument("role", default="member")
    add.add_argument("--approver", action="append", default=[])
    show = sub.add_parser("list", help="List members")
    args = ap.parse_args()

    if args.cmd == "add":
        entry = onboard(args.name, args.key, args.role, args.approver)
        print(json.dumps(entry, indent=2))
    elif args.cmd == "list":
        print(json.dumps(load_members(), indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover
    cli()
