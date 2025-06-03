from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

LOG_PATH = get_log_path("resonite_ritual_rehearsal_engine.jsonl", "RESONITE_REHEARSAL_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def mark_pass(agent: str, artifact: str) -> Dict[str, str]:
    return log_event("pass", {"agent": agent, "artifact": artifact})


def mark_fail(agent: str, artifact: str) -> Dict[str, str]:
    return log_event("fail", {"agent": agent, "artifact": artifact})


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


@app.route("/pass", methods=["POST"])
def api_pass() -> str:
    data = request.get_json() or {}
    return jsonify(mark_pass(str(data.get("agent")), str(data.get("artifact"))))


@app.route("/fail", methods=["POST"])
def api_fail() -> str:
    data = request.get_json() or {}
    return jsonify(mark_fail(str(data.get("agent")), str(data.get("artifact"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    if data.get("result") == "pass":
        return mark_pass(data.get("agent", ""), data.get("artifact", ""))
    return mark_fail(data.get("agent", ""), data.get("artifact", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Festival/Federation Ritual Rehearsal Engine")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("pass", help="Mark agent/artifact passed")
    p.add_argument("agent")
    p.add_argument("artifact")
    p.set_defaults(func=lambda a: print(json.dumps(mark_pass(a.agent, a.artifact), indent=2)))

    f = sub.add_parser("fail", help="Mark agent/artifact failed")
    f.add_argument("agent")
    f.add_argument("artifact")
    f.set_defaults(func=lambda a: print(json.dumps(mark_fail(a.agent, a.artifact), indent=2)))

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
