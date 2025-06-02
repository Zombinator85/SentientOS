from __future__ import annotations
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import presence_ledger as pl
import neos_bridge as nb

LOG_PATH = get_log_path("neos_council.jsonl", "NEOS_COUNCIL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def onboard(keeper: str) -> dict:
    nb.send_message("onboard", f"{keeper} joins the council")
    pl.log(keeper, "onboarded", "council ritual")
    entry = {"timestamp": datetime.utcnow().isoformat(), "keeper": keeper, "event": "onboard"}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Council/Onboarding Engine")
    ap.add_argument("keeper")
    args = ap.parse_args()
    entry = onboard(args.keeper)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
