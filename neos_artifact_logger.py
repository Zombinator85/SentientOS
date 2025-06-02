from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import presence_ledger as pl

LOG_PATH = Path(os.getenv("NEOS_ARTIFACT_LOG", "logs/neos_artifacts.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_artifact(name: str, description: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "description": description,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    pl.log(name, "artifact", description)
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Sanctuary Artifact Logger")
    ap.add_argument("name")
    ap.add_argument("description")
    args = ap.parse_args()
    entry = log_artifact(args.name, args.description)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
