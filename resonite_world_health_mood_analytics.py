from admin_utils import require_admin_banner, require_lumos_approval
"""Resonite Ritual World Health & Mood Analytics

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path


import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_world_health_mood_analytics.jsonl", "RESONITE_WORLD_HEALTH_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def record_health(world: str, metric: str, value: str) -> Dict[str, str]:
    return log_event("health", {"world": world, "metric": metric, "value": value})


def record_mood(world: str, mood: str) -> Dict[str, str]:
    return log_event("mood", {"world": world, "mood": mood})


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


@app.route("/health", methods=["POST"])
def api_health() -> str:
    data = request.get_json() or {}
    return jsonify(record_health(str(data.get("world")), str(data.get("metric")), str(data.get("value"))))


@app.route("/mood", methods=["POST"])
def api_mood() -> str:
    data = request.get_json() or {}
    return jsonify(record_mood(str(data.get("world")), str(data.get("mood"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    action = data.get("action")
    if action == "health":
        return record_health(data.get("world", ""), data.get("metric", ""), data.get("value", ""))
    if action == "mood":
        return record_mood(data.get("world", ""), data.get("mood", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Ritual World Health & Mood Analytics")
    sub = ap.add_subparsers(dest="cmd")

    hl = sub.add_parser("health", help="Record health metric")
    hl.add_argument("world")
    hl.add_argument("metric")
    hl.add_argument("value")
    hl.set_defaults(func=lambda a: print(json.dumps(record_health(a.world, a.metric, a.value), indent=2)))

    md = sub.add_parser("mood", help="Record mood")
    md.add_argument("world")
    md.add_argument("mood")
    md.set_defaults(func=lambda a: print(json.dumps(record_mood(a.world, a.mood), indent=2)))

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
