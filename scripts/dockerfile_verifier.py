from __future__ import annotations
import argparse
import sys
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()
require_lumos_approval()

REQUIRED_PACKAGES = ["build-essential", "libasound2", "python3.11"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Dockerfile contains required packages")
    parser.add_argument("dockerfile", nargs="?", default="Dockerfile", help="Path to Dockerfile")
    args = parser.parse_args()

    path = Path(args.dockerfile)
    if not path.exists():
        print(f"Dockerfile not found: {path}")
        sys.exit(1)
    content = path.read_text(encoding="utf-8")
    missing = [pkg for pkg in REQUIRED_PACKAGES if pkg not in content]
    if missing:
        print("Missing packages: " + ", ".join(missing))
        print("Consider adding them with apt-get install")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
