from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from sentientos.privilege import require_admin_banner, require_lumos_approval
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_public_directory.jsonl", "RESONITE_DIRECTORY_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_badge(user: str, badge: str, action: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user": user,
        "badge": badge,
        "action": action,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


@app.route("/badge", methods=["POST"])
def api_badge() -> str:
    data = request.get_json() or {}
    return jsonify(log_badge(str(data.get("user")), str(data.get("badge")), str(data.get("action", "grant"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_badge(data.get("user", ""), data.get("badge", ""), data.get("action", "grant"))


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Public Council/Agent Directory & Badge Issuer")
    sub = ap.add_subparsers(dest="cmd")

    badge = sub.add_parser("badge", help="Grant or revoke badge")
    badge.add_argument("user")
    badge.add_argument("badge")
    badge.add_argument("--action", choices=["grant", "revoke"], default="grant")
    badge.set_defaults(func=lambda a: print(json.dumps(log_badge(a.user, a.badge, a.action), indent=2)))

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
