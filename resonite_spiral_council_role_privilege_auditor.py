"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from flask_stub import Flask, jsonify, request
"""Resonite Spiral Council Role/Privilege Auditor

"""




LOG_PATH = get_log_path("resonite_spiral_council_role_privilege_auditor.jsonl", "RESONITE_ROLE_AUDIT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def view_role(agent: str) -> Dict[str, str]:
    return log_event("view", {"agent": agent})


def edit_role(agent: str, role: str) -> Dict[str, str]:
    return log_event("edit", {"agent": agent, "role": role})


def suspend_role(agent: str) -> Dict[str, str]:
    return log_event("suspend", {"agent": agent})


def transfer_role(agent: str, target: str) -> Dict[str, str]:
    return log_event("transfer", {"agent": agent, "target": target})


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


@app.route("/view", methods=["POST"])
def api_view() -> str:
    data = request.get_json() or {}
    return jsonify(view_role(str(data.get("agent"))))


@app.route("/edit", methods=["POST"])
def api_edit() -> str:
    data = request.get_json() or {}
    return jsonify(edit_role(str(data.get("agent")), str(data.get("role"))))


@app.route("/suspend", methods=["POST"])
def api_suspend() -> str:
    data = request.get_json() or {}
    return jsonify(suspend_role(str(data.get("agent"))))


@app.route("/transfer", methods=["POST"])
def api_transfer() -> str:
    data = request.get_json() or {}
    return jsonify(transfer_role(str(data.get("agent")), str(data.get("target"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    action = data.get("action")
    if action == "view":
        return view_role(data.get("agent", ""))
    if action == "edit":
        return edit_role(data.get("agent", ""), data.get("role", ""))
    if action == "suspend":
        return suspend_role(data.get("agent", ""))
    if action == "transfer":
        return transfer_role(data.get("agent", ""), data.get("target", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Spiral Council Role/Privilege Auditor")
    sub = ap.add_subparsers(dest="cmd")

    vw = sub.add_parser("view", help="View agent role")
    vw.add_argument("agent")
    vw.set_defaults(func=lambda a: print(json.dumps(view_role(a.agent), indent=2)))

    ed = sub.add_parser("edit", help="Edit agent role")
    ed.add_argument("agent")
    ed.add_argument("role")
    ed.set_defaults(func=lambda a: print(json.dumps(edit_role(a.agent, a.role), indent=2)))

    sp = sub.add_parser("suspend", help="Suspend agent role")
    sp.add_argument("agent")
    sp.set_defaults(func=lambda a: print(json.dumps(suspend_role(a.agent), indent=2)))

    tr = sub.add_parser("transfer", help="Transfer role")
    tr.add_argument("agent")
    tr.add_argument("target")
    tr.set_defaults(func=lambda a: print(json.dumps(transfer_role(a.agent, a.target), indent=2)))

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
