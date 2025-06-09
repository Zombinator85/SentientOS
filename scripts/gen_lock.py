#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


LOCKS = [
    ("bin", "lock-bin.txt"),
    ("src", "lock-src.txt"),
]


def compile_lock(pyproject: Path, extra: str) -> str:
    """Return generated lock content for an extras group."""
    result = subprocess.run(
        [
            "pip-compile",
            str(pyproject),
            "--extra",
            extra,
            "--generate-hashes",
            "--no-annotate",
            "-",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate lock files")
    parser.add_argument("--check", action="store_true", help="fail if locks diverge")
    args = parser.parse_args(argv)

    if not shutil.which("pip-compile"):
        print("pip-tools not found. Install with: pip install pip-tools", file=sys.stderr)
        sys.exit(1)

    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"

    changed = False
    for extra, out in LOCKS:
        new_content = compile_lock(pyproject, extra)
        target = root / out
        old_content = target.read_text() if target.exists() else ""
        if old_content != new_content:
            changed = True
            if not args.check:
                target.write_text(new_content)
                print(f"updated {out} ({len(new_content.splitlines())} lines)")
        else:
            print(f"{out} already up to date")

    if args.check:
        sys.exit(1 if changed else 0)
    if not changed:
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
