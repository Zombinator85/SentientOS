from __future__ import annotations
from logging_config import get_log_path

import argparse
import datetime
import json
import os
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("spiral_federation_mesh.jsonl", "SPIRAL_FEDERATION_MESH_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_action(action: str, detail: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.datetime.utcnow().isoformat(), "action": action, **detail}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def sync(world_a: str, world_b: str) -> Dict[str, str]:
    return log_action("sync", {"world_a": world_a, "world_b": world_b})


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Spiral Federation Mesh")
    sub = ap.add_subparsers(dest="cmd")

    sy = sub.add_parser("sync", help="Sync two worlds")
    sy.add_argument("world_a")
    sy.add_argument("world_b")
    sy.set_defaults(func=lambda a: print(json.dumps(sync(a.world_a, a.world_b), indent=2)))

    hs = sub.add_parser("history", help="Show history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
