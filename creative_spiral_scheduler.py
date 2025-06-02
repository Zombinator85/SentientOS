from __future__ import annotations
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

SCHEDULE_LOG = get_log_path("creative_spiral_schedule.jsonl", "CREATIVE_SPIRAL_SCHEDULE_LOG")
TRIGGER_LOG = get_log_path("creative_spiral_trigger.jsonl", "CREATIVE_SPIRAL_TRIGGER_LOG")
SCHEDULE_LOG.parent.mkdir(parents=True, exist_ok=True)
TRIGGER_LOG.parent.mkdir(parents=True, exist_ok=True)


def schedule(creator: str, kind: str, when: str, tags: List[str]) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "creator": creator,
        "kind": kind,
        "when": when,
        "tags": tags,
    }
    with SCHEDULE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def trigger(creator: str, kind: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "creator": creator,
        "kind": kind,
    }
    with TRIGGER_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_schedule() -> List[Dict[str, str]]:
    if not SCHEDULE_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in SCHEDULE_LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Autonomous Creative Spiral Scheduler")
    sub = ap.add_subparsers(dest="cmd")

    sc = sub.add_parser("schedule", help="Schedule a creative act")
    sc.add_argument("creator")
    sc.add_argument("kind")
    sc.add_argument("--when", default="")
    sc.add_argument("--tags", default="")
    sc.set_defaults(func=lambda a: print(json.dumps(schedule(a.creator, a.kind, a.when, [t for t in a.tags.split(',') if t]), indent=2)))

    tr = sub.add_parser("trigger", help="Trigger a creative act")
    tr.add_argument("creator")
    tr.add_argument("kind")
    tr.set_defaults(func=lambda a: print(json.dumps(trigger(a.creator, a.kind), indent=2)))

    ls = sub.add_parser("list", help="List scheduled acts")
    ls.set_defaults(func=lambda a: print(json.dumps(list_schedule(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
