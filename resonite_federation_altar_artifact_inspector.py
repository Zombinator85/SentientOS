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

LOG_PATH = get_log_path("resonite_artifact_inspector.jsonl", "RESONITE_ARTIFACT_INSPECT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_scan(artifact: str, origin: str, blessed: bool, user: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "artifact": artifact,
        "origin": origin,
        "blessed": blessed,
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
    parser = argparse.ArgumentParser(description="Federation altar artifact inspector")
    sub = parser.add_subparsers(dest="cmd")

    sc = sub.add_parser("scan", help="Scan an artifact")
    sc.add_argument("artifact")
    sc.add_argument("origin")
    sc.add_argument("--blessed", action="store_true")
    sc.add_argument("--user", required=True)

    hs = sub.add_parser("history", help="Show scan history")

    args = parser.parse_args()
    if args.cmd == "scan":
        print(json.dumps(log_scan(args.artifact, args.origin, args.blessed, args.user), indent=2))
    else:
        print(json.dumps(history(), indent=2))


if __name__ == "__main__":
    main()
