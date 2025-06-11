from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

"""Review festival or onboarding curriculum files.

Results are written to ``logs/neos_curriculum_review.jsonl`` or the path
defined by ``NEOS_CURRICULUM_REVIEW_LOG``. See ``docs/ENVIRONMENT.md`` for
details.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_curriculum_review.jsonl", "NEOS_CURRICULUM_REVIEW_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def review_file(path: str) -> Dict[str, int]:
    p = Path(path)
    stats = {
        "lines": 0,
        "todo": 0,
    }
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            stats["lines"] += 1
            if "TODO" in line:
                stats["todo"] += 1
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "file": path,
        "lines": stats["lines"],
        "todo": stats["todo"],
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

def history(limit: int = 20) -> List[Dict[str, int]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, int]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out

def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Festival/Onboarding Curriculum Reviewer")
    sub = ap.add_subparsers(dest="cmd")

    rev = sub.add_parser("review", help="Review curriculum file")
    rev.add_argument("file")
    rev.set_defaults(func=lambda a: print(json.dumps(review_file(a.file), indent=2)))

    hist = sub.add_parser("history", help="Show review history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
