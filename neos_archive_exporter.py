from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""NeosVR Festival/Federation Archive Exporter."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = get_log_path("neos_archive_export.jsonl", "NEOS_ARCHIVE_EXPORT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_export(kind: str, path: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "kind": kind,
        "path": path,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_exports() -> List[Dict[str, str]]:
    return read_json(LOG_PATH)


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Archive Exporter")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log export")
    lg.add_argument("kind")
    lg.add_argument("path")
    lg.set_defaults(func=lambda a: print(json.dumps(log_export(a.kind, a.path), indent=2)))

    ls = sub.add_parser("list", help="List exports")
    ls.set_defaults(func=lambda a: print(json.dumps(list_exports(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
