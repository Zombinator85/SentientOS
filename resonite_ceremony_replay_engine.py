from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Resonite Ceremony Replay/Simulation Engine

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()


import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_ceremony_replay_engine.jsonl", "RESONITE_CEREMONY_REPLAY_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(event: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def record(ceremony_id: str, description: str) -> Dict[str, str]:
    return log_event("record", {"ceremony": ceremony_id, "description": description})


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


@app.route("/record", methods=["POST"])
def api_record() -> str:
    data = request.get_json() or {}
    return jsonify(record(str(data.get("ceremony")), str(data.get("description"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return record(data.get("ceremony", ""), data.get("description", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Ceremony Replay/Simulation Engine")
    sub = ap.add_subparsers(dest="cmd")

    rec = sub.add_parser("record", help="Record ceremony event")
    rec.add_argument("ceremony")
    rec.add_argument("description")
    rec.set_defaults(func=lambda a: print(json.dumps(record(a.ceremony, a.description), indent=2)))

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
