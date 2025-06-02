from __future__ import annotations

"""Avatar Autonomous Ritual Scheduler.

Avatars can request or trigger new rituals. Requests may be reviewed and
approved by council or users. All actions are logged.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from admin_utils import require_admin_banner

REQUEST_LOG = Path(os.getenv("AVATAR_RITUAL_REQUEST_LOG", "logs/avatar_ritual_requests.jsonl"))
APPROVAL_LOG = Path(os.getenv("AVATAR_RITUAL_APPROVAL_LOG", "logs/avatar_ritual_approved.jsonl"))
REQUEST_LOG.parent.mkdir(parents=True, exist_ok=True)
APPROVAL_LOG.parent.mkdir(parents=True, exist_ok=True)


def log_request(avatar: str, ritual: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "ritual": ritual,
        "status": "pending",
    }
    with REQUEST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_requests() -> List[Dict[str, str]]:
    if not REQUEST_LOG.exists():
        return []
    out = []
    for line in REQUEST_LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def approve_request(index: int) -> Dict[str, str]:
    reqs = list_requests()
    if index < 0 or index >= len(reqs):
        raise IndexError("invalid request index")
    entry = reqs[index]
    entry["status"] = "approved"
    with APPROVAL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Avatar Autonomous Ritual Scheduler")
    sub = ap.add_subparsers(dest="cmd")

    rq = sub.add_parser("request", help="Request a ritual")
    rq.add_argument("avatar")
    rq.add_argument("ritual")
    rq.set_defaults(
        func=lambda a: print(json.dumps(log_request(a.avatar, a.ritual), indent=2))
    )

    ls = sub.add_parser("list", help="List pending ritual requests")
    ls.set_defaults(func=lambda a: print(json.dumps(list_requests(), indent=2)))

    apv = sub.add_parser("approve", help="Approve a ritual request by index")
    apv.add_argument("index", type=int)
    apv.set_defaults(
        func=lambda a: print(json.dumps(approve_request(a.index), indent=2))
    )

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
