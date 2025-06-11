"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from flask_stub import Flask, jsonify, request
# Resonite Consent Renewal/Annulment Daemon



LOG_PATH = get_log_path("resonite_consent_daemon.jsonl")
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


def update_consent(user: str, power: str, status: str) -> Dict[str, str]:
    return log_entry("consent", {"user": user, "power": power, "status": status})


@app.route("/consent", methods=["POST"])
def api_consent() -> str:
    data = request.get_json() or {}
    entry = update_consent(str(data.get("user")), str(data.get("power")), str(data.get("status", "renew")))
    return jsonify(entry)


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux placeholder

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_entry("protoflux", data)


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Consent Renewal/Annulment Daemon")
    sub = ap.add_subparsers(dest="cmd")

    up = sub.add_parser("update", help="Update consent")
    up.add_argument("user")
    up.add_argument("power")
    up.add_argument("status", choices=["renew", "pause", "revoke"], default="renew")
    up.set_defaults(func=lambda a: print(json.dumps(update_consent(a.user, a.power, a.status), indent=2)))

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
