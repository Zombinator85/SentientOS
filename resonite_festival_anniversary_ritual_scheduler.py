from __future__ import annotations
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner
import presence_ledger as pl
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
LOG_PATH = get_log_path("resonite_festival_anniversary_scheduler.jsonl", "RESONITE_ANNIVERSARY_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_schedule(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    pl.log("anniversary", action, data.get("note", ""))
    return entry


def schedule(event: str, date: str) -> Dict[str, str]:
    return log_schedule("schedule", {"event": event, "date": date})


def history(limit: int = 20) -> List[Dict[str, str]]:
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


@app.route("/schedule", methods=["POST"])
def api_schedule() -> str:
    data = request.get_json() or {}
    return jsonify(schedule(str(data.get("event")), str(data.get("date"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    if data.get("action") == "schedule":
        return schedule(data.get("event", ""), data.get("date", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Festival/Federation Anniversary Ritual Scheduler")
    sub = ap.add_subparsers(dest="cmd")

    sc = sub.add_parser("schedule", help="Schedule anniversary")
    sc.add_argument("event")
    sc.add_argument("date")
    sc.set_defaults(func=lambda a: print(json.dumps(schedule(a.event, a.date), indent=2)))

    hi = sub.add_parser("history", help="Show history")
    hi.add_argument("--limit", type=int, default=20)
    hi.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
