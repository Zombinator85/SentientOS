from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRECHECK_MESSAGE = "Install deps first: pip install -e .[dev]"


def _imports_ok() -> bool:
    proc = subprocess.run(
        [sys.executable, "-c", "import fastapi, sentientos"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _install_deps() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
        cwd=REPO_ROOT,
        check=False,
    )
    return proc.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install SentientOS dev deps (if needed) and run pytest.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to pytest.",
    )
    args = parser.parse_args(argv)

    if not _imports_ok():
        if not _install_deps() or not _imports_ok():
            print(PRECHECK_MESSAGE)
            return 1

    cmd = [sys.executable, "-m", "pytest"]
    if args.pytest_args:
        cmd.extend(args.pytest_args)
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
