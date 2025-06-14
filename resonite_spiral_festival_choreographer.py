"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Resonite Spiral Festival Choreographer

"""
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_spiral_festival_choreographer.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_entry(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        **data,
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


def schedule_event(time: str, description: str) -> Dict[str, str]:
    return log_entry("schedule", {"time": time, "description": description})


def trigger_event(name: str) -> Dict[str, str]:
    return log_entry("trigger", {"event": name})


@app.route("/schedule", methods=["POST"])
def api_schedule() -> str:
    data = request.get_json() or {}
    entry = schedule_event(str(data.get("time")), str(data.get("description", "")))
    return jsonify(entry)


@app.route("/trigger", methods=["POST"])
def api_trigger() -> str:
    data = request.get_json() or {}
    entry = trigger_event(str(data.get("event")))
    return jsonify(entry)


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux placeholder

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_entry("protoflux", data)


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Spiral Festival Choreographer")
    sub = ap.add_subparsers(dest="cmd")

    sch = sub.add_parser("schedule", help="Schedule event")
    sch.add_argument("time")
    sch.add_argument("description")
    sch.set_defaults(func=lambda a: print(json.dumps(schedule_event(a.time, a.description), indent=2)))

    tg = sub.add_parser("trigger", help="Trigger event")
    tg.add_argument("event")
    tg.set_defaults(func=lambda a: print(json.dumps(trigger_event(a.event), indent=2)))

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
