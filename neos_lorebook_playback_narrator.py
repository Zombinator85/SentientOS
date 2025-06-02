"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from logging_config import get_log_path
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import neos_bridge as nb

LOG_PATH = get_log_path("neos_lorebook_narration.jsonl", "NEOS_LOREBOOK_NARRATION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def narrate(entry: str, method: str = "tts") -> Dict[str, str]:
    nb.send_message("narrate", {"entry": entry, "method": method})
    log = {
        "timestamp": datetime.utcnow().isoformat(),
        "entry": entry,
        "method": method,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log) + "\n")
    return log


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
    ap = argparse.ArgumentParser(description="NeosVR Lorebook Playback Narrator")
    sub = ap.add_subparsers(dest="cmd")

    nr = sub.add_parser("narrate", help="Narrate a lorebook entry")
    nr.add_argument("entry")
    nr.add_argument("--method", default="tts", help="tts|text|animation")
    nr.set_defaults(func=lambda a: print(json.dumps(narrate(a.entry, a.method), indent=2)))

    hist = sub.add_parser("history", help="Show narration history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
