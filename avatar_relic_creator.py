from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("avatar_relics.jsonl", "AVATAR_RELIC_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_relic(avatar: str, relic: str, info: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "relic": relic,
        "info": info,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def extract(avatar: str, relic: str) -> dict[str, Any]:
    """Select memory fragments for ``avatar`` and persist them as a relic."""

    fragments = []
    try:
        import memory_manager as mm

        fragments = mm.search_by_tags([avatar], limit=5)
    except Exception:  # pragma: no cover - optional dependency failures
        fragments = []

    info = {"fragments": [f.get("text", "") for f in fragments]}
    if not info["fragments"]:
        info["note"] = "relic placeholder"

    return log_relic(avatar, relic, info)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Avatar heirloom and relic creator")
    ap.add_argument("avatar")
    ap.add_argument("relic")
    args = ap.parse_args()
    entry = extract(args.avatar, args.relic)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
