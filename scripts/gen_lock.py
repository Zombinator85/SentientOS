#!/usr/bin/env python3
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
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


def extras_with_requirements(pyproject: Path) -> list[str]:
    import tomllib

    data = tomllib.loads(pyproject.read_text())
    extras = data.get("project", {}).get("optional-dependencies", {})
    return [
        name
        for name, pkgs in extras.items()
        if any(p.strip().startswith("-r") for p in pkgs)
    ]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate lock files")
    parser.add_argument("--check", action="store_true", help="fail if locks diverge")
    parser.add_argument("--strict", action="store_true", help="error on extras referencing -r")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"

    if args.strict:
        offenders = extras_with_requirements(pyproject)
        if offenders:
            print("extras referencing -r detected:", ", ".join(offenders), file=sys.stderr)
            sys.exit(1)

    if not shutil.which("pip-compile"):
        print("pip-tools not found. Install with: pip install pip-tools", file=sys.stderr)
        sys.exit(1)

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
