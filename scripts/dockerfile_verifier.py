from __future__ import annotations
import argparse
import sys
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Check a Dockerfile for required SentientOS build packages."""

# Check a Dockerfile for required SentientOS build packages.

# Check a Dockerfile for required SentientOS build packages.

# Check a Dockerfile for required SentientOS build packages.

require_admin_banner()
require_lumos_approval()

REQUIRED = ["build-essential", "libasound2", "python3.11"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify required packages in Dockerfile"
    )
    parser.add_argument("--dockerfile", default="Dockerfile", help="Path to Dockerfile")
    args = parser.parse_args()

    path = Path(args.dockerfile)
    if not path.exists():
        print(f"Dockerfile not found: {path}")
        sys.exit(1)

    content = path.read_text(encoding="utf-8")
    missing = [pkg for pkg in REQUIRED if pkg not in content]
    if missing:
        print("Missing packages: " + ", ".join(missing))
        print("Hint: apt-get install " + " ".join(missing))
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
