"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Automated script to migrate NeosVR references to Resonite."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import platform_succession as ps


RE_NEOSVR = re.compile(r"NeosVR")
RE_NEOS_PREFIX = re.compile(r"neos_")


def replace_in_file(path: Path, user: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text = RE_NEOSVR.sub("Resonite", text)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        ps.log_event(user, "replace", [str(path)], note="NeosVR to Resonite")

    if RE_NEOS_PREFIX.search(path.name):
        new_name = RE_NEOS_PREFIX.sub("resonite_", path.name)
        new_path = path.with_name(new_name)
        path.rename(new_path)
        ps.log_event(user, "rename", [str(path), str(new_path)], note="neos_ prefix")


def update_imports(root: Path, user: str) -> None:
    for p in root.rglob("*.py"):
        replace_in_file(p, user)


def main() -> None:
    parser = argparse.ArgumentParser(description="Automated Resonite migration")
    parser.add_argument("user", help="user performing migration")
    parser.add_argument("root", nargs="?", default=".", help="project root")
    args = parser.parse_args()
    update_imports(Path(args.root), args.user)


if __name__ == "__main__":
    main()
