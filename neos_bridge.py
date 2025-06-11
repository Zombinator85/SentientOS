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

BRIDGE_DIR = Path(os.getenv("NEOS_BRIDGE_DIR", "C:/SentientOS/neos"))
BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = get_log_path("neos_bridge.jsonl", "NEOS_BRIDGE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def send_message(category: str, text: str) -> Dict[str, str]:
    """Write ``text`` to the bridge folder and log the event."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "category": category,
        "text": text,
    }
    file_path = BRIDGE_DIR / f"{category}_{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
    file_path.write_text(text, encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    """Return recent bridge events."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Bridge Connector")
    sub = ap.add_subparsers(dest="cmd")

    snd = sub.add_parser("send", help="Send a message")
    snd.add_argument("category")
    snd.add_argument("text")
    snd.set_defaults(func=lambda a: print(json.dumps(send_message(a.category, a.text), indent=2)))

    tst = sub.add_parser("test", help="Send a test presence message")
    tst.set_defaults(func=lambda a: print(json.dumps(send_message("test", "presence ping"), indent=2)))

    hist = sub.add_parser("history", help="Show bridge history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
