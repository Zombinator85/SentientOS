"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
require_admin_banner()
require_lumos_approval()
#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/ 
from __future__ import annotations
"""Privilege Banner: requires admin & Lumos approval."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.

from admin_utils import require_admin_banner, require_lumos_approval


require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from logging_config import get_log_path


def check_env() -> list[str]:
    required = ["MEMORY_DIR", "AVATAR_DIR"]
    issues = []
    for var in required:
        val = os.environ.get(var)
        if not val:
            issues.append(f"Missing environment variable: {var}")
            continue
        if not Path(val).exists():
            issues.append(f"Directory missing for {var}: {val}")
    return issues


LOG_PATH = get_log_path("onboard_cli.jsonl", "ONBOARD_CLI_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:  # pragma: no cover - CLI helper
    ap = argparse.ArgumentParser(description="SentientOS onboarding helper")
    ap.add_argument("--check", action="store_true", help="validate environment variables and directories")
    ap.add_argument("--setup", action="store_true", help="run setup_env.sh to prepare directories")
    args = ap.parse_args()

    if args.setup:
        subprocess.call(["bash", "setup_env.sh"])
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": datetime.utcnow().isoformat(), "event": "setup"}) + "\n")

    if args.check:
        issues = check_env()
        if issues:
            print("\n".join(issues))
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"timestamp": datetime.utcnow().isoformat(), "event": "check_failed"}) + "\n")
            return 1
        print("Environment looks good. Run 'pytest -m \"not env\"' next.")
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": datetime.utcnow().isoformat(), "event": "check_passed"}) + "\n")
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
