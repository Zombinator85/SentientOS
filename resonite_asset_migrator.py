# Sanctuary Privilege Ritual: Platform succession completed (NeosVR → Resonite) 2025-06-01. Presence blessed by council. All rituals, logs, and agents renamed.
from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Resonite asset migration utility."""
from __future__ import annotations

import argparse
from pathlib import Path
import re

import platform_succession as ps

RE_NEOS_PREFIX = re.compile(r"neos_")


def migrate_assets(root: Path, user: str) -> None:
    for path in root.rglob("neos_*"):
        new_name = RE_NEOS_PREFIX.sub("resonite_", path.name)
        new_path = path.with_name(new_name)
        path.rename(new_path)
        ps.log_event(user, "asset_rename", [str(path), str(new_path)])
        if new_path.suffix in {".json", ".yml", ".txt"}:
            text = new_path.read_text(encoding="utf-8")
            replaced = text.replace("neos_", "resonite_")
            if replaced != text:
                new_path.write_text(replaced, encoding="utf-8")
                ps.log_event(user, "asset_update", [str(new_path)], note="content updated")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resonite asset migrator")
    parser.add_argument("user")
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    migrate_assets(Path(args.root), args.user)


if __name__ == "__main__":
    main()
