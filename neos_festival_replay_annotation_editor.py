from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

ANNOTATION_LOG = Path(
    os.getenv("NEOS_FESTIVAL_REPLAY_ANNOTATION_LOG", "logs/neos_festival_replay_annotations.jsonl")
)
ANNOTATION_LOG.parent.mkdir(parents=True, exist_ok=True)


def add_annotation(timestamp: str, note: str, author: str) -> Dict[str, str]:
    entry = {
        "timestamp": timestamp,
        "note": note,
        "author": author,
        "logged": datetime.utcnow().isoformat(),
    }
    with ANNOTATION_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_annotations(term: str = "") -> List[Dict[str, str]]:
    if not ANNOTATION_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in ANNOTATION_LOG.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if term and term not in json.dumps(rec):
            continue
        out.append(rec)
    return out


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Festival Replay Annotation Editor")
    sub = ap.add_subparsers(dest="cmd")

    addp = sub.add_parser("add", help="Add annotation")
    addp.add_argument("timestamp")
    addp.add_argument("note")
    addp.add_argument("--author", default="council")
    addp.set_defaults(func=lambda a: print(json.dumps(add_annotation(a.timestamp, a.note, a.author), indent=2)))

    lst = sub.add_parser("list", help="List annotations")
    lst.add_argument("--term", default="")
    lst.set_defaults(func=lambda a: print(json.dumps(list_annotations(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
