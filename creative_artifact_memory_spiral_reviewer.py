from __future__ import annotations

"""Creative/Artifact Memory Spiral Reviewer
Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("SPIRAL_REVIEW_LOG", "logs/spiral_review.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def review(note: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "note": note}
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


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Creative/Artifact Memory Spiral Reviewer")
    sub = ap.add_subparsers(dest="cmd")

    rv = sub.add_parser("review", help="Record a spiral review")
    rv.add_argument("note")
    rv.set_defaults(func=lambda a: print(json.dumps(review(a.note), indent=2)))

    hs = sub.add_parser("history", help="Show review history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
