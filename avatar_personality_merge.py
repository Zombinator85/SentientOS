from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from typing import Any


from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

LOG_PATH = get_log_path("avatar_merge.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
MEMORY_PATH = get_log_path("avatar_memory_link.jsonl", "AVATAR_MEMORY_LINK_LOG")


def log_merge(new_avatar: str, parents: list[str], info: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": new_avatar,
        "parents": parents,
        "info": info,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def merge(a: str, b: str, name: str) -> dict[str, Any]:
    """Merge avatar memory links under a new identity."""
    merged: list[dict[str, Any]] = []
    if MEMORY_PATH.exists():
        lines = MEMORY_PATH.read_text(encoding="utf-8").splitlines()
        for ln in lines:
            try:
                entry = json.loads(ln)
            except Exception:
                continue
            if entry.get("avatar") in {a, b}:
                entry["avatar"] = name
                merged.append(entry)
        if merged:
            need_nl = MEMORY_PATH.read_text(encoding="utf-8").endswith("\n")
            with MEMORY_PATH.open("a", encoding="utf-8") as f:
                if not need_nl:
                    f.write("\n")
                for entry in merged:
                    f.write(json.dumps(entry) + "\n")
    info = {"merged": len(merged)}
    return log_merge(name, [a, b], info)


def main() -> None:
    require_admin_banner()
    import argparse

    ap = argparse.ArgumentParser(description="Avatar personality merge ritual")
    ap.add_argument("avatar_a")
    ap.add_argument("avatar_b")
    ap.add_argument("name")
    args = ap.parse_args()
    entry = merge(args.avatar_a, args.avatar_b, args.name)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
