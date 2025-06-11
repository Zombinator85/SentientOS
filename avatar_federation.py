from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Export and import avatars with ritual logs."""
from logging_config import get_log_path

import argparse
import json
import os
import tarfile
from datetime import datetime
from pathlib import Path

EXPORT_LOG = get_log_path("avatar_export.jsonl", "AVATAR_EXPORT_LOG")
IMPORT_LOG = get_log_path("avatar_import.jsonl", "AVATAR_IMPORT_LOG")
for p in (EXPORT_LOG, IMPORT_LOG):
    p.parent.mkdir(parents=True, exist_ok=True)


def _log(path: Path, reason: str, log_path: Path) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "path": str(path),
        "reason": reason,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def export_avatar(avatar: Path, out: Path, reason: str) -> Path:
    with tarfile.open(out, "w:gz") as tar:
        tar.add(avatar, arcname=avatar.name)
    _log(out, reason, EXPORT_LOG)
    return out


def import_avatar(tar_path: Path, dest: Path, reason: str) -> Path:
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(dest)
    _log(dest, reason, IMPORT_LOG)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description="Federation avatar exchange")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export")
    ex.add_argument("avatar")
    ex.add_argument("out")
    ex.add_argument("--reason", default="")

    im = sub.add_parser("import")
    im.add_argument("tar")
    im.add_argument("dest")
    im.add_argument("--reason", default="")

    args = ap.parse_args()
    if args.cmd == "export":
        path = export_avatar(Path(args.avatar), Path(args.out), args.reason)
    else:
        path = import_avatar(Path(args.tar), Path(args.dest), args.reason)
    print(str(path))


if __name__ == "__main__":
    main()
