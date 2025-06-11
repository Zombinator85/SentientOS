"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from logging_config import get_log_path
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

import argparse
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List

import audit_immutability as ai
from log_utils import append_json, read_json

from admin_utils import require_admin_banner, require_lumos_approval

LOG_PATH = get_log_path("archive_blessing.jsonl", "ARCHIVE_BLESSING_LOG")
ARCHIVE_DIR = Path(os.getenv("ARCHIVE_DIR", "archives"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def seal_log(log: Path, curator: str) -> Dict[str, str]:
    """Verify and seal a log into the archive directory."""
    verified = ai.verify(log)
    digest = hashlib.sha256(log.read_bytes()).hexdigest()
    ts = datetime.datetime.utcnow().isoformat()
    name = f"{log.stem}_{ts.replace(':', '-')}.gz"
    archive_path = ARCHIVE_DIR / name
    with gzip.open(archive_path, "wb") as f:
        f.write(log.read_bytes())
    entry = {
        "timestamp": ts,
        "log": str(log),
        "archive": str(archive_path),
        "digest": digest,
        "verified": verified,
        "curator": curator,
    }
    append_json(LOG_PATH, entry)
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    return read_json(LOG_PATH)[-limit:]


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Archive blessing ceremony")
    sub = ap.add_subparsers(dest="cmd")

    seal = sub.add_parser("seal", help="Seal a log file")
    seal.add_argument("log")
    seal.add_argument("curator")
    seal.set_defaults(func=lambda a: print(json.dumps(seal_log(Path(a.log), a.curator), indent=2)))

    hist = sub.add_parser("history", help="Show ceremony history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
