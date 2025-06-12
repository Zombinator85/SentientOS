"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from __future__ import annotations
from logging_config import get_log_path




import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_festival_stream.jsonl", "NEOS_FESTIVAL_STREAM_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(event: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event, **data}
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
    ap = argparse.ArgumentParser(description="NeosVR Festival Ceremony Live Streamer")
    sub = ap.add_subparsers(dest="cmd")

    st = sub.add_parser("start", help="Log stream start")
    st.add_argument("title")
    st.set_defaults(func=lambda a: print(json.dumps(log_event("stream_start", {"title": a.title}), indent=2)))

    vi = sub.add_parser("viewer", help="Log viewer join")
    vi.add_argument("name")
    vi.set_defaults(func=lambda a: print(json.dumps(log_event("viewer", {"name": a.name}), indent=2)))

    fb = sub.add_parser("feedback", help="Log feedback")
    fb.add_argument("user")
    fb.add_argument("message")
    fb.set_defaults(func=lambda a: print(json.dumps(log_event("feedback", {"user": a.user, "message": a.message}), indent=2)))

    bl = sub.add_parser("blessing", help="Log blessing event")
    bl.add_argument("issuer")
    bl.add_argument("blessing")
    bl.set_defaults(func=lambda a: print(json.dumps(log_event("blessing", {"issuer": a.issuer, "blessing": a.blessing}), indent=2)))

    hist = sub.add_parser("history", help="Show stream history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
