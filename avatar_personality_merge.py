from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from typing import Any


from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = get_log_path("avatar_merge.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


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
    """Placeholder avatar merge ritual."""
    # TODO: merge mood and memory logs
    info = {"note": "merge placeholder"}
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
