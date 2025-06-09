#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


LOCKS = [
    ("bin", "lock-bin.txt"),
    ("src", "lock-src.txt"),
]


def main() -> None:
    if not shutil.which("pip-compile"):
        print("pip-tools not found. Install with: pip install pip-tools", file=sys.stderr)
        sys.exit(1)
    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"
    for extra, out in LOCKS:
        subprocess.run(
            ["pip-compile", str(pyproject), "--extra", extra, "-o", str(root / out)],
            check=True,
        )
    print("Lock files generated")


if __name__ == "__main__":  # pragma: no cover
    main()
