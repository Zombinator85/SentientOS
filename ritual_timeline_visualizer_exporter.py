from __future__ import annotations

"""Ritual Timeline Visualizer/Exporter
Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("RITUAL_TIMELINE_LOG", "logs/ritual_timeline.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(event: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event}
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


def export(dest: Path, limit: int = 100) -> Path:
    dest.write_text(json.dumps(history(limit), indent=2), encoding="utf-8")
    return dest


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Ritual Timeline Visualizer/Exporter")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log timeline event")
    lg.add_argument("event")
    lg.set_defaults(func=lambda a: print(json.dumps(log_event(a.event), indent=2)))

    hs = sub.add_parser("history", help="Show timeline history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    ex = sub.add_parser("export", help="Export timeline")
    ex.add_argument("dest")
    ex.add_argument("--limit", type=int, default=100)
    ex.set_defaults(func=lambda a: print(str(export(Path(a.dest), a.limit))))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
