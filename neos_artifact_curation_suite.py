from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""NeosVR Artifact Audit & Curation Suite."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_artifact_curation.jsonl", "NEOS_ARTIFACT_CURATION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_action(artifact: str, action: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "artifact": artifact,
        "action": action,
        "note": note,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_actions(term: str = "") -> List[Dict[str, str]]:
    acts = read_json(LOG_PATH)
    if term:
        acts = [a for a in acts if term in json.dumps(a)]
    return acts


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Artifact Curation Suite")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log curation action")
    lg.add_argument("artifact")
    lg.add_argument("action")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_action(a.artifact, a.action, a.note), indent=2)))

    ls = sub.add_parser("list", help="List actions")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_actions(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
