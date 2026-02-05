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


def _emit_run_context(install_performed: bool, pytest_args: list[str]) -> None:
    joined_args = " ".join(pytest_args) if pytest_args else "(none)"
    print(
        "run_tests: "
        f"python={sys.executable} "
        f"install_performed={install_performed} "
        f"pytest_args={joined_args}"
    )


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

    install_performed = False
    if not _imports_ok():
        install_performed = True
        if not _install_deps() or not _imports_ok():
            _emit_run_context(install_performed, args.pytest_args)
            print(PRECHECK_MESSAGE)
            return 1

    _emit_run_context(install_performed, args.pytest_args)
    cmd = [sys.executable, "-m", "pytest"]
    if args.pytest_args:
        cmd.extend(args.pytest_args)
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
