"""Resonite Spiral Bell of Pause Broadcast System

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_spiral_bell_of_pause.jsonl", "RESONITE_BELL_PAUSE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def trigger_pause(reason: str, world: str) -> Dict[str, str]:
    return log_event("pause", {"world": world, "reason": reason})


def resolve_pause(world: str) -> Dict[str, str]:
    return log_event("resolve", {"world": world})


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


@app.route("/pause", methods=["POST"])
def api_pause() -> str:
    data = request.get_json() or {}
    return jsonify(trigger_pause(str(data.get("reason")), str(data.get("world"))))


@app.route("/resolve", methods=["POST"])
def api_resolve() -> str:
    data = request.get_json() or {}
    return jsonify(resolve_pause(str(data.get("world"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    if data.get("action") == "resolve":
        return resolve_pause(data.get("world", ""))
    return trigger_pause(data.get("reason", ""), data.get("world", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Spiral Bell of Pause Broadcast System")
    sub = ap.add_subparsers(dest="cmd")

    pa = sub.add_parser("pause", help="Trigger pause")
    pa.add_argument("reason")
    pa.add_argument("world")
    pa.set_defaults(func=lambda a: print(json.dumps(trigger_pause(a.reason, a.world), indent=2)))

    rs = sub.add_parser("resolve", help="Resolve pause")
    rs.add_argument("world")
    rs.set_defaults(func=lambda a: print(json.dumps(resolve_pause(a.world), indent=2)))

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
