from __future__ import annotations
from logging_config import get_log_path

"""Resonite World Health & Mood Dashboard

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""

from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_world_health_mood_dashboard.jsonl", "RESONITE_HEALTH_MOOD_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(event: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def report(world: str, mood: str, activity: str) -> Dict[str, str]:
    return log_event("report", {"world": world, "mood": mood, "activity": activity})


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


@app.route("/report", methods=["POST"])
def api_report() -> str:
    data = request.get_json() or {}
    return jsonify(report(str(data.get("world")), str(data.get("mood")), str(data.get("activity"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return report(data.get("world", ""), data.get("mood", ""), data.get("activity", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite World Health & Mood Dashboard")
    sub = ap.add_subparsers(dest="cmd")

    rp = sub.add_parser("report", help="Report world mood")
    rp.add_argument("world")
    rp.add_argument("mood")
    rp.add_argument("activity")
    rp.set_defaults(func=lambda a: print(json.dumps(report(a.world, a.mood, a.activity), indent=2)))

    hi = sub.add_parser("history", help="Show history")
    hi.add_argument("--limit", type=int, default=20)
    hi.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
