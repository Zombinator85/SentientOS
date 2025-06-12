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

import presence_ledger as pl
from flask_stub import Flask, jsonify, request
LOG_PATH = get_log_path("resonite_consent_feedback_wizard.jsonl", "RESONITE_CONSENT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_path(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    pl.log("consent_wizard", action, data.get("user", ""))
    return entry


def onboard(user: str) -> Dict[str, str]:
    return log_path("onboard", {"user": user})


def feedback(user: str, text: str) -> Dict[str, str]:
    return log_path("feedback", {"user": user, "text": text})


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


@app.route("/onboard", methods=["POST"])
def api_onboard() -> str:
    data = request.get_json() or {}
    return jsonify(onboard(str(data.get("user"))))


@app.route("/feedback", methods=["POST"])
def api_feedback() -> str:
    data = request.get_json() or {}
    return jsonify(feedback(str(data.get("user")), str(data.get("text"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    action = data.get("action")
    if action == "onboard":
        return onboard(data.get("user", ""))
    if action == "feedback":
        return feedback(data.get("user", ""), data.get("text", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Guest & Agent Consent/Feedback Wizard")
    sub = ap.add_subparsers(dest="cmd")

    ob = sub.add_parser("onboard", help="Record onboarding")
    ob.add_argument("user")
    ob.set_defaults(func=lambda a: print(json.dumps(onboard(a.user), indent=2)))

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


if __name__ == "__main__":  # pragma: no cover
    main()
