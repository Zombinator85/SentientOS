"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/ 
from __future__ import annotations
"""Privilege Banner: requires admin & Lumos approval."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.

import argparse
import experiment_tracker as et
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
from admin_utils import require_admin_banner, require_lumos_approval



def main() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    parser = argparse.ArgumentParser(description=ENTRY_BANNER)
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("propose")
    p.add_argument("description")
    p.add_argument("conditions")
    p.add_argument("expected")
    p.add_argument("--user")

    l = sub.add_parser("list")
    l.add_argument("--status")

    v = sub.add_parser("vote")
    v.add_argument("id")
    v.add_argument("--user", required=True)
    v.add_argument("--down", action="store_true")

    c = sub.add_parser("comment")
    c.add_argument("id")
    c.add_argument("text")
    c.add_argument("--user", required=True)

    s = sub.add_parser("set-status")
    s.add_argument("id")
    s.add_argument("status")

    args = parser.parse_args()
    print_banner()

    if args.cmd == "propose":
        eid = et.propose_experiment(
            args.description,
            args.conditions,
            args.expected,
            proposer=args.user,
        )
        print(eid)
    elif args.cmd == "list":
        for info in et.list_experiments(args.status):
            rate = info.get("success", 0) / max(1, info.get("triggers", 1))
            print(info["id"], info.get("status"), f"{rate:.2f}", info.get("description"))
    elif args.cmd == "vote":
        et.vote_experiment(args.id, args.user, upvote=not args.down)
    elif args.cmd == "comment":
        et.comment_experiment(args.id, args.user, args.text)
    elif args.cmd == "set-status":
        et.update_status(args.id, args.status)
    else:
        parser.print_help()
    print_closing()


if __name__ == "__main__":
    main()
