from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Resonite Cross-World Ceremony Orchestrator

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()


import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("resonite_cross_world_ceremony_orchestrator.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(action: str, info: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **info}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_event("protoflux", data)


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Cross-World Ceremony Orchestrator")
    sub = ap.add_subparsers(dest="cmd")

    sch = sub.add_parser("schedule", help="Schedule ceremony")
    sch.add_argument("name")
    sch.add_argument("--time", default="")
    sch.set_defaults(func=lambda a: print(json.dumps(log_event("schedule", {"name": a.name, "time": a.time}), indent=2)))

    view = sub.add_parser("history", help="Show history")
    view.add_argument("--limit", type=int, default=20)
    view.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
