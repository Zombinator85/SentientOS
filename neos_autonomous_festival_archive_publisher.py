from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_festival_archive.jsonl", "NEOS_FESTIVAL_ARCHIVE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def publish_archive(archive: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "archive": archive,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_publications(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Autonomous Festival Archive Publisher")
    sub = ap.add_subparsers(dest="cmd")

    pub = sub.add_parser("publish", help="Publish archive")
    pub.add_argument("archive")
    pub.add_argument("--note", default="")
    pub.set_defaults(func=lambda a: print(json.dumps(publish_archive(a.archive, a.note), indent=2)))

    ls = sub.add_parser("list", help="List publications")
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=lambda a: print(json.dumps(list_publications(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
