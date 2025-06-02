from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("NEOS_RITUAL_TIMELINE_LOG", "logs/neos_ritual_timeline.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def export_timeline(paths: List[str], dest: str) -> Dict[str, str]:
    events: List[Dict[str, str]] = []
    for name in paths:
        p = Path(name)
        if not p.exists():
            continue
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                data = json.loads(ln)
                ts = data.get("timestamp")
                if ts:
                    events.append({"timestamp": ts, "source": name, **data})
            except Exception:
                continue
    events.sort(key=lambda e: e.get("timestamp", ""))
    Path(dest).write_text(json.dumps(events, indent=2), encoding="utf-8")
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "dest": dest,
        "events": len(events),
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
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Ritual Timeline Exporter")
    sub = ap.add_subparsers(dest="cmd")

    ex = sub.add_parser("export", help="Export timeline")
    ex.add_argument("dest")
    ex.add_argument("logs", nargs="+")
    ex.set_defaults(func=lambda a: print(json.dumps(export_timeline(a.logs, a.dest), indent=2)))

    hist = sub.add_parser("history", help="Show export history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
