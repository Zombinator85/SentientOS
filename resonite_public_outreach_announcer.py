from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Resonite Public Blessing/Outreach Announcer

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

LOG_PATH = get_log_path("resonite_public_outreach_announcer.jsonl", "RESONITE_OUTREACH_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def broadcast(message: str, author: str) -> Dict[str, str]:
    return log_event("broadcast", {"message": message, "author": author})


def feedback(user: str, text: str) -> Dict[str, str]:
    return log_event("feedback", {"user": user, "text": text})


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


@app.route("/broadcast", methods=["POST"])
def api_broadcast() -> str:
    data = request.get_json() or {}
    return jsonify(broadcast(str(data.get("message")), str(data.get("author"))))


@app.route("/feedback", methods=["POST"])
def api_feedback() -> str:
    data = request.get_json() or {}
    return jsonify(feedback(str(data.get("user")), str(data.get("text"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    action = data.get("action")
    if action == "feedback":
        return feedback(data.get("user", ""), data.get("text", ""))
    if action == "broadcast":
        return broadcast(data.get("message", ""), data.get("author", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Public Blessing/Outreach Announcer")
    sub = ap.add_subparsers(dest="cmd")

    bc = sub.add_parser("broadcast", help="Broadcast message")
    bc.add_argument("message")
    bc.add_argument("author")
    bc.set_defaults(func=lambda a: print(json.dumps(broadcast(a.message, a.author), indent=2)))

    fb = sub.add_parser("feedback", help="Record feedback")
    fb.add_argument("user")
    fb.add_argument("text")
    fb.set_defaults(func=lambda a: print(json.dumps(feedback(a.user, a.text), indent=2)))

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
