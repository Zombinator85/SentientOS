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
import json
import heresy_log
from admin_utils import require_admin_banner, require_lumos_approval


"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
def main() -> None:
    require_admin_banner()
    parser = argparse.ArgumentParser(description="Heresy log CLI")
    sub = parser.add_subparsers(dest="cmd")
    log_cmd = sub.add_parser("log", help="Record a heresy entry")
    log_cmd.add_argument("action")
    log_cmd.add_argument("requestor")
    log_cmd.add_argument("detail")
    sub.add_parser("list", help="Show recent entries")
    search_cmd = sub.add_parser("search", help="Search log")
    search_cmd.add_argument("term")
    parser.add_argument("--limit", type=int, default=10, help="List limit")
    args = parser.parse_args()

    if args.cmd == "log":
        heresy_log.log(args.action, args.requestor, args.detail)
        print("Logged")
    elif args.cmd == "search":
        res = heresy_log.search(args.term)
        print(json.dumps(res, indent=2))
    else:
        res = heresy_log.tail(args.limit)
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
