"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from logging_config import get_log_path
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

ANIMATION_LOG = get_log_path("law_lore_animation.jsonl", "LAW_LORE_ANIMATION_LOG")
ANIMATION_LOG.parent.mkdir(parents=True, exist_ok=True)


def animate(action: str, scene: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "scene": scene,
    }
    with ANIMATION_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not ANIMATION_LOG.exists():
        return []
    lines = ANIMATION_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="In-World Law/Lore Animation Orchestrator")
    sub = ap.add_subparsers(dest="cmd")

    an = sub.add_parser("animate", help="Log animation action")
    an.add_argument("action")
    an.add_argument("scene")
    an.set_defaults(func=lambda a: print(json.dumps(animate(a.action, a.scene), indent=2)))

    ls = sub.add_parser("history", help="Show animation log")
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
