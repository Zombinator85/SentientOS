#!/usr/bin/env python3
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""
"""
from __future__ import annotations
# Automate release version bumping and tagging.
import argparse
import datetime as dt
import os
import re
import subprocess
from pathlib import Path

try:
    import tomllib
except Exception:  # Python <3.11
    import tomli as tomllib  # type: ignore[import-not-found]  # fallback for Python <3.11


PYPROJECT = Path("pyproject.toml")
CHANGELOG = Path("docs/CHANGELOG.md")


def read_version() -> str:
    if PYPROJECT.exists():
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        return str(data["project"]["version"])
    raise FileNotFoundError("pyproject.toml not found")


def write_version(version: str) -> None:
    """Update the version string in pyproject.toml."""
    text = PYPROJECT.read_text(encoding="utf-8")
    new_text = re.sub(
        r"(^version\s*=\s*)\"[^\"]+\"",
        f"\\1\"{version}\"",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(new_text, encoding="utf-8")


def bump_patch(version: str) -> str:
    major, minor, patch = map(int, version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def update_changelog(version: str) -> None:
    date = dt.date.today().isoformat()
    entry = f"## [{version}] - {date}\n- TBD\n"
    text = CHANGELOG.read_text(encoding="utf-8")
    CHANGELOG.write_text(text + "\n" + entry, encoding="utf-8")


def git(*args: str) -> None:
    subprocess.run(["git", *args], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release manager")
    parser.add_argument("--dry-run", action="store_true", help="Do not modify files")
    args = parser.parse_args(argv)

    old = read_version()
    new = bump_patch(old)
    print(f"Bumping {old} -> {new}")

    if args.dry_run:
        return 0

    write_version(new)
    update_changelog(new)
    git("add", str(PYPROJECT), str(CHANGELOG))
    git("commit", "-m", f"Release v{new}")
    git("tag", f"v{new}")
    git("push")
    git("push", "origin", f"v{new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
