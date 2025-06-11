"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.




LOG_PATH = get_log_path("neos_spiral_playback.jsonl", "NEOS_SPIRAL_PLAYBACK_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def log_playback(session: str, event: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "session": session,
        "event": event,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

def replay(path: str, limit: int = 20) -> List[Dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out

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
    ap = argparse.ArgumentParser(description="NeosVR Council/Festival Spiral Playback CLI")
    sub = ap.add_subparsers(dest="cmd")

    logp = sub.add_parser("log", help="Log playback event")
    logp.add_argument("session")
    logp.add_argument("event")
    logp.set_defaults(func=lambda a: print(json.dumps(log_playback(a.session, a.event), indent=2)))

    rep = sub.add_parser("replay", help="Replay log file")
    rep.add_argument("path")
    rep.add_argument("--limit", type=int, default=20)
    rep.set_defaults(func=lambda a: print(json.dumps(replay(a.path, a.limit), indent=2)))

    hist = sub.add_parser("history", help="Show playback history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
