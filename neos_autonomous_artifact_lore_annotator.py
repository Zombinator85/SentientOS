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

LOG_PATH = get_log_path("neos_artifact_lore.jsonl", "NEOS_ARTIFACT_LORE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def annotate(artifact: str, lore: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "artifact": artifact,
        "lore": lore,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def annotations(term: str = "") -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if term and term not in json.dumps(rec):
            continue
        out.append(rec)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Autonomous Artifact Lore Annotator")
    sub = ap.add_subparsers(dest="cmd")

    ann = sub.add_parser("annotate", help="Annotate artifact")
    ann.add_argument("artifact")
    ann.add_argument("lore")
    ann.set_defaults(func=lambda a: print(json.dumps(annotate(a.artifact, a.lore), indent=2)))

    ls = sub.add_parser("list", help="List annotations")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(annotations(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
