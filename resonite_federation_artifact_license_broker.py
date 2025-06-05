from admin_utils import require_admin_banner, require_lumos_approval
"""Resonite Federation/Artifact License Broker

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path


import argparse
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_federation_artifact_license_broker.jsonl", "RESONITE_LICENSE_BROKER_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def request_license(artifact: str, requester: str) -> Dict[str, str]:
    req_id = str(uuid.uuid4())
    return log_event("request", {"id": req_id, "artifact": artifact, "requester": requester})


def approve_license(req_id: str, approver: str) -> Dict[str, str]:
    return log_event("approve", {"id": req_id, "approver": approver})


def view_license(artifact: str) -> Dict[str, str]:
    return log_event("view", {"artifact": artifact})


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


@app.route("/request", methods=["POST"])
def api_request() -> str:
    data = request.get_json() or {}
    return jsonify(request_license(str(data.get("artifact")), str(data.get("requester"))))


@app.route("/approve", methods=["POST"])
def api_approve() -> str:
    data = request.get_json() or {}
    return jsonify(approve_license(str(data.get("id")), str(data.get("approver"))))


@app.route("/view", methods=["POST"])
def api_view() -> str:
    data = request.get_json() or {}
    return jsonify(view_license(str(data.get("artifact"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    action = data.get("action")
    if action == "request":
        return request_license(data.get("artifact", ""), data.get("requester", ""))
    if action == "approve":
        return approve_license(data.get("id", ""), data.get("approver", ""))
    if action == "view":
        return view_license(data.get("artifact", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Federation/Artifact License Broker")
    sub = ap.add_subparsers(dest="cmd")

    rq = sub.add_parser("request", help="Request license")
    rq.add_argument("artifact")
    rq.add_argument("requester")
    rq.set_defaults(func=lambda a: print(json.dumps(request_license(a.artifact, a.requester), indent=2)))

    apv = sub.add_parser("approve", help="Approve license")
    apv.add_argument("id")
    apv.add_argument("approver")
    apv.set_defaults(func=lambda a: print(json.dumps(approve_license(a.id, a.approver), indent=2)))

    vw = sub.add_parser("view", help="View license")
    vw.add_argument("artifact")
    vw.set_defaults(func=lambda a: print(json.dumps(view_license(a.artifact), indent=2)))

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
