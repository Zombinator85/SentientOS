from __future__ import annotations

"""Artifact/Lore Self-Healing Engine
Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("ARTIFACT_HEAL_LOG", "logs/artifact_heal.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_action(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def scan() -> List[str]:
    missing = ["artifact1", "lore2"]
    log_action("scan", {"missing": ",".join(missing)})
    return missing


def heal(patch: str) -> Dict[str, str]:
    return log_action("heal", {"patch": patch})


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
    ap = argparse.ArgumentParser(description="Artifact/Lore Self-Healing Engine")
    sub = ap.add_subparsers(dest="cmd")

    sc = sub.add_parser("scan", help="Scan for missing artifacts")
    sc.set_defaults(func=lambda a: print(json.dumps(scan(), indent=2)))

    hl = sub.add_parser("heal", help="Apply healing patch")
    hl.add_argument("patch")
    hl.set_defaults(func=lambda a: print(json.dumps(heal(a.patch), indent=2)))

    hs = sub.add_parser("history", help="Show heal history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
