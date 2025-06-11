"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List
require_admin_banner()
require_lumos_approval()
VOTE_LOG = get_log_path("neos_festival_law_votes.jsonl", "NEOS_FESTIVAL_LAW_VOTE_LOG")
VOTE_LOG.parent.mkdir(parents=True, exist_ok=True)


def propose(amendment: str, proposer: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "amendment": amendment,
        "proposer": proposer,
        "votes": [],
    }
    with VOTE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def vote(index: int, voter: str, choice: str) -> Dict[str, str]:
    if not VOTE_LOG.exists():
        return {}
    lines = VOTE_LOG.read_text(encoding="utf-8").splitlines()
    if index < 0 or index >= len(lines):
        return {}
    rec = json.loads(lines[index])
    rec.setdefault("votes", []).append(
        {"voter": voter, "choice": choice, "timestamp": datetime.utcnow().isoformat()}
    )
    lines[index] = json.dumps(rec)
    VOTE_LOG.write_text("\n".join(lines), encoding="utf-8")
    return rec


def list_votes() -> List[Dict[str, str]]:
    if not VOTE_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in VOTE_LOG.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Festival Law Review & Council Vote CLI")
    sub = ap.add_subparsers(dest="cmd")

    pp = sub.add_parser("propose", help="Propose amendment")
    pp.add_argument("amendment")
    pp.add_argument("--proposer", default="council")
    pp.set_defaults(func=lambda a: print(json.dumps(propose(a.amendment, a.proposer), indent=2)))

    vt = sub.add_parser("vote", help="Cast vote")
    vt.add_argument("index", type=int)
    vt.add_argument("voter")
    vt.add_argument("choice")
    vt.set_defaults(func=lambda a: print(json.dumps(vote(a.index, a.voter, a.choice), indent=2)))

    ls = sub.add_parser("list", help="List votes")
    ls.set_defaults(func=lambda a: print(json.dumps(list_votes(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
