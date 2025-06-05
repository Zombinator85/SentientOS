from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from pathlib import Path
from datetime import datetime

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_provenance_queries.jsonl", "RESONITE_PROVENANCE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

ARTIFACT_DB = get_log_path("artifacts.jsonl", "RESONITE_ARTIFACT_DB")


def query(artifact: str) -> dict | None:
    if not ARTIFACT_DB.exists():
        return None
    for line in ARTIFACT_DB.read_text(encoding="utf-8").splitlines():
        data = json.loads(line)
        if data.get("name") == artifact:
            return data
    return None


def log_query(user: str, artifact: str) -> None:
    entry = {"timestamp": datetime.utcnow().isoformat(), "user": user, "artifact": artifact}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def explore(user: str, artifact: str) -> None:
    require_admin_banner()
    log_query(user, artifact)
    data = query(artifact)
    if data:
        print(json.dumps(data, indent=2))
    else:
        print("Artifact not found")


def main() -> None:
    parser = argparse.ArgumentParser(description="Presence/Artifact provenance explorer")
    parser.add_argument("user")
    parser.add_argument("artifact")
    args = parser.parse_args()
    explore(args.user, args.artifact)


if __name__ == "__main__":
    main()
