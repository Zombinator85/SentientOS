from __future__ import annotations
from logging_config import get_log_path

"""Resonite Ritual Breach Response System

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

LOG_PATH = get_log_path("resonite_ritual_breach_response_system.jsonl", "RESONITE_BREACH_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(event: str, info: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event, **info}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def escalate(reason: str, world: str) -> Dict[str, str]:
    return log_event("escalate", {"reason": reason, "world": world})


def lockdown(world: str) -> Dict[str, str]:
    return log_event("lockdown", {"world": world})


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


@app.route("/escalate", methods=["POST"])
def api_escalate() -> str:
    data = request.get_json() or {}
    return jsonify(escalate(str(data.get("reason")), str(data.get("world"))))


@app.route("/lockdown", methods=["POST"])
def api_lockdown() -> str:
    data = request.get_json() or {}
    return jsonify(lockdown(str(data.get("world"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    if data.get("action") == "lockdown":
        return lockdown(data.get("world", ""))
    return escalate(data.get("reason", ""), data.get("world", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Ritual Breach Response System")
    sub = ap.add_subparsers(dest="cmd")

    es = sub.add_parser("escalate", help="Escalate breach")
    es.add_argument("reason")
    es.add_argument("world")
    es.set_defaults(func=lambda a: print(json.dumps(escalate(a.reason, a.world), indent=2)))

    ld = sub.add_parser("lockdown", help="Lock down world")
    ld.add_argument("world")
    ld.set_defaults(func=lambda a: print(json.dumps(lockdown(a.world), indent=2)))

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
