from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
# Build documentation using mkdocs.

require_admin_banner()
require_lumos_approval()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build project documentation")
    parser.parse_args()

    config = Path("mkdocs.yml")
    if not config.exists():
        print("mkdocs.yml not found")
        sys.exit(1)

    result = subprocess.run(["mkdocs", "build", "--clean"])
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
