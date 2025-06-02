from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("NEOS_ASSET_LOG", "logs/neos_model_assets.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def generate_asset(agent: str, asset_type: str, emotion: str, memory: str) -> Dict[str, str]:
    """Record an autonomous asset generation entry."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent": agent,
        "asset_type": asset_type,
        "emotion": emotion,
        "memory": memory,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


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


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Autonomous Model Asset Generator")
    sub = ap.add_subparsers(dest="cmd")

    gen = sub.add_parser("generate", help="Generate an asset entry")
    gen.add_argument("agent")
    gen.add_argument("asset_type")
    gen.add_argument("emotion")
    gen.add_argument("memory")
    gen.set_defaults(func=lambda a: print(json.dumps(generate_asset(a.agent, a.asset_type, a.emotion, a.memory), indent=2)))

    hist = sub.add_parser("history", help="Show asset history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
