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

LOG_PATH = get_log_path("resonite_agent_onboarding.jsonl", "RESONITE_AGENT_ONBOARDING_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_registration(agent: str, ring: str, user: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent": agent,
        "ring": ring,
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
    parser = argparse.ArgumentParser(description="Agent onboarding/ordination suite")
    sub = parser.add_subparsers(dest="cmd")

    reg = sub.add_parser("register", help="Register an agent")
    reg.add_argument("agent")
    reg.add_argument("ring")
    reg.add_argument("user")

    hs = sub.add_parser("history", help="Show onboardings")

    args = parser.parse_args()
    if args.cmd == "register":
        print(json.dumps(log_registration(args.agent, args.ring, args.user), indent=2))
    else:
        print(json.dumps(history(), indent=2))


if __name__ == "__main__":
    main()
