"""Avatar Council Blessing

Council members vote on major avatars. Votes are logged and a final blessing
is recorded once quorum is reached.

Example:
    python avatar_council_blessing.py vote avatar1 alice
    python avatar_council_blessing.py status avatar1 --quorum 2
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("AVATAR_COUNCIL_LOG", "logs/avatar_council_log.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_vote(avatar: str, member: str, up: bool = True, commentary: str = "") -> Dict[str, str]:
    """Record a council vote for an avatar."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "member": member,
        "vote": "up" if up else "down",
        "commentary": commentary,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def votes_for(avatar: str) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if f'"avatar": "{avatar}"' not in line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def check_quorum(avatar: str, quorum: int = 3) -> bool:
    vs = votes_for(avatar)
    up = sum(1 for v in vs if v.get("vote") == "up")
    if up >= quorum:
        blessing = {
            "timestamp": datetime.utcnow().isoformat(),
            "avatar": avatar,
            "event": "crowned",
            "blessing": "Council quorum achieved",
        }
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(blessing) + "\n")
        return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar council blessing")
    sub = ap.add_subparsers(dest="cmd")

    vt = sub.add_parser("vote", help="Cast a vote")
    vt.add_argument("avatar")
    vt.add_argument("member")
    vt.add_argument("--down", action="store_true")
    vt.add_argument("--commentary", default="")
    vt.set_defaults(
        func=lambda a: print(
            json.dumps(
                log_vote(a.avatar, a.member, up=not a.down, commentary=a.commentary),
                indent=2,
            )
        )
    )

    st = sub.add_parser("status", help="Check vote status")
    st.add_argument("avatar")
    st.add_argument("--quorum", type=int, default=3)
    st.set_defaults(
        func=lambda a: print(
            json.dumps({"quorum_met": check_quorum(a.avatar, a.quorum)}, indent=2)
        )
    )

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
