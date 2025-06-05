from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Autonomous Self-Patching Agent
Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("self_patch_agent.jsonl", "SELF_PATCH_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def propose(description: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "description": description, "status": "proposed"}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def apply(patch_id: int) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "patch_id": patch_id, "status": "applied"}
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


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Autonomous Self-Patching Agent")
    sub = ap.add_subparsers(dest="cmd")

    pr = sub.add_parser("propose", help="Propose a patch")
    pr.add_argument("description")
    pr.set_defaults(func=lambda a: print(json.dumps(propose(a.description), indent=2)))

    aply = sub.add_parser("apply", help="Apply a patch")
    aply.add_argument("patch_id", type=int)
    aply.set_defaults(func=lambda a: print(json.dumps(apply(a.patch_id), indent=2)))

    hs = sub.add_parser("history", help="Show patch history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
