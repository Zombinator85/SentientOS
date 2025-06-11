from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from sentientos.privilege import require_admin_banner, require_lumos_approval
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_feedback_portal.jsonl", "RESONITE_FEEDBACK_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_feedback(user: str, text: str, urgent: bool = False) -> Dict[str, Any]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "text": text,
        "urgent": urgent,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


@app.route("/submit", methods=["POST"])
def api_submit() -> str:
    data = request.get_json() or {}
    return jsonify(log_feedback(str(data.get("user")), str(data.get("text")), bool(data.get("urgent"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, Any]:
    return log_feedback(data.get("user", ""), data.get("text", ""), bool(data.get("urgent")))


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Cathedral Council Public Feedback Portal")
    sub = ap.add_subparsers(dest="cmd")

    subm = sub.add_parser("submit", help="Submit feedback")
    subm.add_argument("user")
    subm.add_argument("text")
    subm.add_argument("--urgent", action="store_true")
    subm.set_defaults(func=lambda a: print(json.dumps(log_feedback(a.user, a.text, a.urgent), indent=2)))

    hist = sub.add_parser("history", help="Show history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
