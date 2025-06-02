from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("NEOS_SELF_HEALING_LAW_LOG", "logs/neos_self_healing_law.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def propose_fix(issue: str, proposal: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "issue": issue,
        "proposal": proposal,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_proposals(term: str = "") -> List[Dict[str, str]]:
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
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Self-Healing Ritual Law Editor")
    sub = ap.add_subparsers(dest="cmd")

    pf = sub.add_parser("propose", help="Propose fix")
    pf.add_argument("issue")
    pf.add_argument("proposal")
    pf.set_defaults(func=lambda a: print(json.dumps(propose_fix(a.issue, a.proposal), indent=2)))

    ls = sub.add_parser("list", help="List proposals")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_proposals(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
