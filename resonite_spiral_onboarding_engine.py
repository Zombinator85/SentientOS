from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_spiral_onboarding.jsonl", "RESONITE_SPIRAL_ONBOARDING_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_step(user: str, step: str) -> dict:
    entry = {"timestamp": datetime.utcnow().isoformat(), "user": user, "step": step}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def run_spiral(user: str) -> None:
    steps = [
        "declare_intent",
        "council_invocation",
        "privilege_banner",
        "memory_blessing",
    ]
    for step in steps:
        entry = log_step(user, step)
        print(json.dumps(entry))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Resonite spiral onboarding ritual")
    parser.add_argument("user")
    args = parser.parse_args()
    run_spiral(args.user)


if __name__ == "__main__":
    main()
