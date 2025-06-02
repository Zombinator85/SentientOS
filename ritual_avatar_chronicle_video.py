from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
"""Ritual Avatar Chronicle-to-Video Compiler.

Creates placeholder video compilations from ritual logs.
"""

import argparse
import json
import os
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_chronicle_video.jsonl", "AVATAR_CHRONICLE_VIDEO_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def compile_chronicle(name: str, logs: List[Path], out: Path) -> Path:
    with tarfile.open(out, "w:gz") as tar:
        for fp in logs:
            tar.add(fp, arcname=fp.name)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "archive": str(out),
        "logs": [str(p) for p in logs],
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return out


def list_compilations() -> List[Dict[str, str]]:
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
    ap = argparse.ArgumentParser(description="Avatar Chronicle to Video")
    sub = ap.add_subparsers(dest="cmd")

    cp = sub.add_parser("compile", help="Compile ritual logs")
    cp.add_argument("name")
    cp.add_argument("out")
    cp.add_argument("logs", nargs="+")
    cp.set_defaults(func=lambda a: print(compile_chronicle(a.name, [Path(p) for p in a.logs], Path(a.out))))

    ls = sub.add_parser("list", help="List compilations")
    ls.set_defaults(func=lambda a: print(json.dumps(list_compilations(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
