from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
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

LOG_PATH = get_log_path("neos_presence_pulse.jsonl", "NEOS_PULSE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def send_pulse(pulse_type: str, mood: str = "") -> Dict[str, str]:
    """Record a presence pulse event."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "type": pulse_type,
        "mood": mood,
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
    ap = argparse.ArgumentParser(description="NeosVR Presence Pulse Beacon")
    sub = ap.add_subparsers(dest="cmd")

    pulse = sub.add_parser("pulse", help="Send presence pulse")
    pulse.add_argument("type")
    pulse.add_argument("--mood", default="")
    pulse.set_defaults(func=lambda a: print(json.dumps(send_pulse(a.type, a.mood), indent=2)))

    hist = sub.add_parser("history", help="Show pulse history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
