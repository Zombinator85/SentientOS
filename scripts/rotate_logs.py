"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
"""Rotate SentientOS logs weekly or when they exceed the configured size."""

import os
import datetime as dt
import gzip
from pathlib import Path
from typing import Optional

from logging_config import get_log_dir, get_log_path
from log_utils import append_json

MAX_SIZE_MB = int(os.getenv("MAX_LOG_SIZE_MB", "10"))
ROTATE_WEEKLY = os.getenv("LOG_ROTATE_WEEKLY", "true").lower() == "true"
ARCHIVE_DIR = get_log_dir() / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
ROTATION_LOG = get_log_path("log_rotation.jsonl")


def _should_rotate(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, ""
    reason_parts = []
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        reason_parts.append("size")
    if ROTATE_WEEKLY:
        mtime = dt.datetime.utcfromtimestamp(path.stat().st_mtime)
        if (dt.datetime.utcnow() - mtime).days >= 7:
            reason_parts.append("weekly")
    return bool(reason_parts), "+".join(reason_parts)


def _rotate(path: Path, reason: str) -> None:
    ts = dt.datetime.utcnow().isoformat()
    archive_name = f"{path.stem}_{ts.replace(':', '-')}.jsonl.gz"
    archive_path = ARCHIVE_DIR / archive_name
    with gzip.open(archive_path, "wb") as gz:
        gz.write(path.read_bytes())
    path.write_text("", encoding="utf-8")
    entry = {
        "timestamp": ts,
        "log": str(path),
        "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
        "reason": reason,
        "archive": str(archive_path),
    }
    append_json(ROTATION_LOG, entry)


def rotate_all() -> None:
    log_dir = get_log_dir()
    for log_file in log_dir.glob("*.jsonl"):
        rotate_one(log_file)


def rotate_one(log_file: Path) -> Optional[Path]:
    do_rotate, reason = _should_rotate(log_file)
    if not do_rotate:
        return None
    _rotate(log_file, reason)
    return ARCHIVE_DIR / f"{log_file.stem}_*"


def main() -> None:  # pragma: no cover - CLI
    rotate_all()
    print("Log rotation complete")


if __name__ == "__main__":
    main()
