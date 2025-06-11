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

LOG_PATH = get_log_path("resonite_artifact_blessing_inspector.jsonl", "RESONITE_ARTIFACT_BLESSING_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_review(artifact: str, reviewer: str, verdict: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "artifact": artifact,
        "reviewer": reviewer,
        "verdict": verdict,
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
    parser = argparse.ArgumentParser(description="Artifact blessing inspector")
    sub = parser.add_subparsers(dest="cmd")

    rv = sub.add_parser("review", help="Review an artifact")
    rv.add_argument("artifact")
    rv.add_argument("reviewer")
    rv.add_argument("verdict")

    hs = sub.add_parser("history", help="Show reviews")

    args = parser.parse_args()
    if args.cmd == "review":
        print(json.dumps(log_review(args.artifact, args.reviewer, args.verdict), indent=2))
    else:
        print(json.dumps(history(), indent=2))


if __name__ == "__main__":
    main()
