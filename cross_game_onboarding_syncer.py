from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

SYNC_LOG = get_log_path("onboarding_sync.jsonl", "ONBOARDING_SYNC_LOG")
SYNC_LOG.parent.mkdir(parents=True, exist_ok=True)


def record(user: str, world: str, stage: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "world": world,
        "stage": stage,
    }
    with SYNC_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def progress(user: str) -> List[Dict[str, str]]:
    if not SYNC_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in SYNC_LOG.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if obj.get("user") == user:
            out.append(obj)
    return out


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Cross-Game/Cathedral Onboarding Syncer")
    sub = ap.add_subparsers(dest="cmd")

    rec = sub.add_parser("record", help="Record progress")
    rec.add_argument("user")
    rec.add_argument("world")
    rec.add_argument("stage")
    rec.set_defaults(func=lambda a: print(json.dumps(record(a.user, a.world, a.stage), indent=2)))

    pg = sub.add_parser("progress", help="Show progress")
    pg.add_argument("user")
    pg.set_defaults(func=lambda a: print(json.dumps(progress(a.user), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
