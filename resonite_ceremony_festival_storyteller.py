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

LOG_PATH = get_log_path("resonite_storyteller.jsonl", "RESONITE_STORYTELLER_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_story(title: str, content: str) -> dict:
    entry = {"timestamp": datetime.utcnow().isoformat(), "title": title, "content": content}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def narrate(title: str, content: str) -> None:
    require_admin_banner()
    entry = log_story(title, content)
    print(json.dumps(entry, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ceremony/Festival storyteller")
    parser.add_argument("title")
    parser.add_argument("content")
    args = parser.parse_args()
    narrate(args.title, args.content)


if __name__ == "__main__":
    main()
