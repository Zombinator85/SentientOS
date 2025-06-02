from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
"""Ritual Avatar Festival Memory Capsule."""

import argparse
import json
import os
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_festival_capsules.jsonl", "AVATAR_FESTIVAL_CAPSULE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def create_capsule(name: str, files: List[Path], out: Path) -> Path:
    with tarfile.open(out, "w:gz") as tar:
        for fp in files:
            tar.add(fp, arcname=fp.name)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "capsule": str(out),
        "files": [str(f) for f in files],
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return out


def list_capsules() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Festival Memory Capsule")
    sub = ap.add_subparsers(dest="cmd")

    cr = sub.add_parser("create", help="Create a memory capsule")
    cr.add_argument("name")
    cr.add_argument("out")
    cr.add_argument("files", nargs="+")
    cr.set_defaults(func=lambda a: print(create_capsule(a.name, [Path(f) for f in a.files], Path(a.out))))

    ls = sub.add_parser("list", help="List capsules")
    ls.set_defaults(func=lambda a: print(json.dumps(list_capsules(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
