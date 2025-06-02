from __future__ import annotations
from logging_config import get_log_path

"""Avatar Autonomous Blessing Proposal Engine."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

PROPOSAL_LOG = get_log_path("avatar_blessing_proposals.jsonl", "AVATAR_BLESSING_PROPOSAL_LOG")
APPROVAL_LOG = get_log_path("avatar_blessing_approved.jsonl", "AVATAR_BLESSING_APPROVAL_LOG")
for p in (PROPOSAL_LOG, APPROVAL_LOG):
    p.parent.mkdir(parents=True, exist_ok=True)


def propose(avatar: str, mood: str, reason: str, line: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "mood": mood,
        "reason": reason,
        "line": line,
        "status": "pending",
    }
    with PROPOSAL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_proposals() -> List[Dict[str, str]]:
    if not PROPOSAL_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in PROPOSAL_LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def approve(index: int) -> Dict[str, str]:
    proposals = list_proposals()
    if index < 0 or index >= len(proposals):
        raise IndexError("invalid proposal index")
    entry = proposals[index]
    entry["status"] = "approved"
    with APPROVAL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Blessing Proposal Engine")
    sub = ap.add_subparsers(dest="cmd")

    pr = sub.add_parser("propose", help="Propose a new blessing")
    pr.add_argument("avatar")
    pr.add_argument("mood")
    pr.add_argument("reason")
    pr.add_argument("line")
    pr.set_defaults(func=lambda a: print(json.dumps(propose(a.avatar, a.mood, a.reason, a.line), indent=2)))

    ls = sub.add_parser("list", help="List blessing proposals")
    ls.set_defaults(func=lambda a: print(json.dumps(list_proposals(), indent=2)))

    apv = sub.add_parser("approve", help="Approve a proposal by index")
    apv.add_argument("index", type=int)
    apv.set_defaults(func=lambda a: print(json.dumps(approve(a.index), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
