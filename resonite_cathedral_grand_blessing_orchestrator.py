from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_cathedral_grand_blessing.jsonl", "RESONITE_GRAND_BLESSING_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(step: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "step": step, **data}
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
    ap = argparse.ArgumentParser(description="Cathedral Grand Blessing Ceremony Orchestrator")
    sub = ap.add_subparsers(dest="cmd")

    step = sub.add_parser("step", help="Record ceremony step")
    step.add_argument("name")
    step.add_argument("actor")
    step.set_defaults(func=lambda a: print(json.dumps(log_event(a.name, {"actor": a.actor}), indent=2)))

    hist = sub.add_parser("history", help="Show history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
