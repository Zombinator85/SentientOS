"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

"""Avatar Sanctuary Artifacts Generator."""


LOG_PATH = get_log_path("avatar_sanctuary_artifacts.jsonl", "AVATAR_ARTIFACT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def create_artifact(creator: str, kind: str, description: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "creator": creator,
        "kind": kind,
        "description": description,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_artifacts() -> List[Dict[str, str]]:
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
    ap = argparse.ArgumentParser(description="Sanctuary Artifacts Generator")
    sub = ap.add_subparsers(dest="cmd")

    cr = sub.add_parser("create", help="Create an artifact")
    cr.add_argument("creator")
    cr.add_argument("kind")
    cr.add_argument("description")
    cr.set_defaults(func=lambda a: print(json.dumps(create_artifact(a.creator, a.kind, a.description), indent=2)))

    ls = sub.add_parser("list", help="List artifacts")
    ls.set_defaults(func=lambda a: print(json.dumps(list_artifacts(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
