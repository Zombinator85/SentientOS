from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""NeosVR Council/Teaching Onboarding Spiral Engine."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_onboarding_spiral.jsonl", "NEOS_ONBOARDING_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_step(user: str, step: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "step": step,
        "note": note,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_steps(user: str = "") -> List[Dict[str, str]]:
    steps = read_json(LOG_PATH)
    if user:
        steps = [s for s in steps if s.get("user") == user]
    return steps


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Onboarding Spiral Engine")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log onboarding step")
    lg.add_argument("user")
    lg.add_argument("step")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_step(a.user, a.step, a.note), indent=2)))

    ls = sub.add_parser("list", help="List steps")
    ls.add_argument("--user", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_steps(a.user), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
