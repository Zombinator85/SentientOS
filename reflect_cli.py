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
import reflection_stream as rs
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()


def main(argv=None):
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    parser = argparse.ArgumentParser(description=ENTRY_BANNER)
    sub = parser.add_subparsers(dest="cmd")
    log = sub.add_parser("log", help="Show recent reflection events")
    log.add_argument("--last", type=int, default=5)
    exp = sub.add_parser("explain", help="Show details of an event")
    exp.add_argument("id")
    sub.add_parser("stats", help="Show event statistics")

    args = parser.parse_args(argv)
    print_banner()
    if args.cmd == "log":
        print(json.dumps(rs.recent(args.last), indent=2))
    elif args.cmd == "explain":
        print(json.dumps(rs.get(args.id), indent=2))
    elif args.cmd == "stats":
        print(json.dumps(rs.stats(), indent=2))
    else:
        parser.print_help()
    print_closing()


if __name__ == "__main__":
    main()
