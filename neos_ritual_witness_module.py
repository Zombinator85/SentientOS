from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_ritual_witnesses.jsonl", "NEOS_WITNESS_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def add_witness(event: str, witness: str) -> Dict[str, str]:
    """Record a witness to a ritual event."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        "witness": witness,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_witnesses(event: str = "") -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(ln)
        except Exception:
            continue
        if event and e.get("event") != event:
            continue
        out.append(e)
    return out


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Ritual Witness Module")
    sub = ap.add_subparsers(dest="cmd")

    addp = sub.add_parser("add", help="Add witness")
    addp.add_argument("event")
    addp.add_argument("witness")
    addp.set_defaults(func=lambda a: print(json.dumps(add_witness(a.event, a.witness), indent=2)))

    lst = sub.add_parser("list", help="List witnesses")
    lst.add_argument("--event", default="")
    lst.set_defaults(func=lambda a: print(json.dumps(list_witnesses(a.event), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
