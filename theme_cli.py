"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
require_admin_banner()
require_lumos_approval()
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
import daily_theme
from admin_utils import require_admin_banner, require_lumos_approval
from typing import Optional


def main() -> None:
    require_admin_banner()
    parser = argparse.ArgumentParser(description="Daily theme tool")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("generate", help="Generate today's theme")
    sub.add_parser("show", help="Show latest theme")
    args = parser.parse_args()

    if args.cmd == "generate":
        theme: Optional[str] = daily_theme.generate()
        print(theme)
    else:
        theme: Optional[str] = daily_theme.latest()
        if theme:
            print(theme)
        else:
            print("No theme yet")


if __name__ == "__main__":
    main()
