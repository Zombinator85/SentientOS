from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Resonite Ritual Proposal & Voting Dashboard

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()


import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import uuid

LOG_PATH = get_log_path("resonite_ritual_proposal_voting_dashboard.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_entry(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        **data,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Ritual Proposal & Voting Dashboard")
    sub = ap.add_subparsers(dest="cmd")

    pr = sub.add_parser("propose", help="Propose ritual")
    pr.add_argument("title")
    pr.add_argument("description")
    pr.set_defaults(func=lambda a: print(json.dumps(log_entry("propose", {"title": a.title, "description": a.description}), indent=2)))

    vt = sub.add_parser("vote", help="Vote on ritual")
    vt.add_argument("proposal_id")
    vt.add_argument("member")
    vt.add_argument("vote", choices=["yes", "no", "abstain"], default="yes")
    vt.set_defaults(func=lambda a: print(json.dumps(log_entry("vote", {"proposal_id": a.proposal_id, "member": a.member, "vote": a.vote}), indent=2)))

    hist = sub.add_parser("history", help="View proposal history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
