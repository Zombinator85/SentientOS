"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from __future__ import annotations
from logging_config import get_log_path




import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_lore_reenactor.jsonl", "NEOS_LORE_REENACT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_reenactment(story: str, actor: str, mode: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "story": story,
        "actor": actor,
        "mode": mode,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Lore Spiral Reenactor")
    sub = ap.add_subparsers(dest="cmd")

    rc = sub.add_parser("reenact", help="Log a lore reenactment")
    rc.add_argument("story")
    rc.add_argument("actor")
    rc.add_argument("mode")
    rc.set_defaults(func=lambda a: print(json.dumps(log_reenactment(a.story, a.actor, a.mode), indent=2)))

    hist = sub.add_parser("history", help="Show reenactment history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
