from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

REQUEST_LOG = Path(os.getenv("NEOS_SCRIPT_REQUEST_LOG", "logs/neos_script_requests.jsonl"))
APPROVAL_LOG = Path(os.getenv("NEOS_SCRIPT_APPROVAL_LOG", "logs/neos_script_approvals.jsonl"))
for p in (REQUEST_LOG, APPROVAL_LOG):
    p.parent.mkdir(parents=True, exist_ok=True)


def request_script(agent: str, name: str, purpose: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent": agent,
        "name": name,
        "purpose": purpose,
        "status": "pending",
    }
    with REQUEST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_requests() -> List[Dict[str, str]]:
    if not REQUEST_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in REQUEST_LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def approve(index: int, reviewer: str) -> Dict[str, str]:
    reqs = list_requests()
    if index < 0 or index >= len(reqs):
        raise IndexError("invalid request index")
    entry = reqs[index]
    entry["status"] = "approved"
    entry["reviewer"] = reviewer
    with APPROVAL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Model-Initiated Script Builder")
    sub = ap.add_subparsers(dest="cmd")

    req = sub.add_parser("request", help="Request a script")
    req.add_argument("agent")
    req.add_argument("name")
    req.add_argument("purpose")
    req.set_defaults(func=lambda a: print(json.dumps(request_script(a.agent, a.name, a.purpose), indent=2)))

    ls = sub.add_parser("list", help="List script requests")
    ls.set_defaults(func=lambda a: print(json.dumps(list_requests(), indent=2)))

    apv = sub.add_parser("approve", help="Approve a request by index")
    apv.add_argument("index", type=int)
    apv.add_argument("reviewer")
    apv.set_defaults(func=lambda a: print(json.dumps(approve(a.index, a.reviewer), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
