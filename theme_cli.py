"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
import argparse
import daily_theme
from admin_utils import require_admin_banner, require_lumos_approval
from typing import Optional
require_admin_banner()
require_lumos_approval()
def main() -> None:
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
