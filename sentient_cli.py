import argparse
import os
import requests
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()


def main(argv=None) -> None:
    require_admin_banner()
    parser = argparse.ArgumentParser(prog="sentientos", description="SentientOS command line")
    parser.add_argument("command", nargs="?", default="status", help="command to run")
    args = parser.parse_args(argv)

    if args.command == "status":
        url = os.getenv("SENTIENTOS_STATUS_URL", "http://localhost:5000/status")
        resp = requests.get(url, timeout=5)
        print(resp.json())
    else:
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
