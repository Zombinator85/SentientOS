from __future__ import annotations
from logging_config import get_log_path

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

LOG_PATH = get_log_path("avatar_cross_presence.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_meeting(source: str, target: str, info: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "target": target,
        "info": info,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def meet(source: str, target: str) -> dict[str, Any]:
    """Exchange an avatar bundle and record a federation handshake."""
    info: dict[str, Any] = {}
    try:
        src = Path(source)
        dest = Path(target)
        if src.is_file() and dest.is_dir():
            import tarfile

            bundle = dest / f"{src.name}.tar.gz"
            with tarfile.open(bundle, "w:gz") as tar:
                tar.add(src, arcname=src.name)
            with tarfile.open(bundle, "r:gz") as tar:
                tar.extractall(dest)
            info["bundle"] = str(bundle)

        from federation_trust_protocol import handshake

        handshake(f"{src.stem}_to_{dest.name}", "auto", "blessed")
        info["handshake"] = True
    except Exception as exc:  # pragma: no cover - unexpected errors
        info = {"error": str(exc)}
    return log_meeting(source, target, info)


def main() -> None:
    require_admin_banner()
    import argparse

    ap = argparse.ArgumentParser(description="Avatar cross presence collaboration")
    ap.add_argument("source")
    ap.add_argument("target")
    args = ap.parse_args()
    entry = meet(args.source, args.target)
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
