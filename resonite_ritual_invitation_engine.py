"""Resonite Ritual Invitation Engine

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner
from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_ritual_invitation_engine.jsonl")
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


def create_invite(code: str, target: str, ritual: str) -> Dict[str, str]:
    return log_entry("invite", {"code": code, "target": target, "ritual": ritual})


def respond_invite(code: str, user: str, response: str) -> Dict[str, str]:
    return log_entry("response", {"code": code, "user": user, "response": response})


@app.route("/invite", methods=["POST"])
def api_invite() -> str:
    data = request.get_json() or {}
    entry = create_invite(str(data.get("code")), str(data.get("target")), str(data.get("ritual", "")))
    return jsonify(entry)


@app.route("/respond", methods=["POST"])
def api_respond() -> str:
    data = request.get_json() or {}
    entry = respond_invite(str(data.get("code")), str(data.get("user")), str(data.get("response", "accept")))
    return jsonify(entry)


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux placeholder

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_entry("protoflux", data)


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Ritual Invitation Engine")
    sub = ap.add_subparsers(dest="cmd")

    inv = sub.add_parser("invite", help="Create invitation")
    inv.add_argument("code")
    inv.add_argument("target")
    inv.add_argument("ritual")
    inv.set_defaults(func=lambda a: print(json.dumps(create_invite(a.code, a.target, a.ritual), indent=2)))

    rs = sub.add_parser("respond", help="Respond to invite")
    rs.add_argument("code")
    rs.add_argument("user")
    rs.add_argument("--response", default="accept")
    rs.set_defaults(func=lambda a: print(json.dumps(respond_invite(a.code, a.user, a.response), indent=2)))

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
