from __future__ import annotations

"""Resonite Spiral Artifact License/Access Controller

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

LOG_PATH = Path(os.getenv("RESONITE_LICENSE_LOG", "logs/resonite_spiral_artifact_license_access_controller.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def grant(artifact: str, user: str, license_type: str) -> Dict[str, str]:
    return log_event("grant", {"artifact": artifact, "user": user, "license": license_type})


def revoke(artifact: str, user: str) -> Dict[str, str]:
    return log_event("revoke", {"artifact": artifact, "user": user})


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


@app.route("/grant", methods=["POST"])
def api_grant() -> str:
    data = request.get_json() or {}
    return jsonify(grant(str(data.get("artifact")), str(data.get("user")), str(data.get("license"))))


@app.route("/revoke", methods=["POST"])
def api_revoke() -> str:
    data = request.get_json() or {}
    return jsonify(revoke(str(data.get("artifact")), str(data.get("user"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    if data.get("action") == "revoke":
        return revoke(data.get("artifact", ""), data.get("user", ""))
    return grant(data.get("artifact", ""), data.get("user", ""), data.get("license", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Spiral Artifact License/Access Controller")
    sub = ap.add_subparsers(dest="cmd")

    gr = sub.add_parser("grant", help="Grant license")
    gr.add_argument("artifact")
    gr.add_argument("user")
    gr.add_argument("license")
    gr.set_defaults(func=lambda a: print(json.dumps(grant(a.artifact, a.user, a.license), indent=2)))

    rv = sub.add_parser("revoke", help="Revoke license")
    rv.add_argument("artifact")
    rv.add_argument("user")
    rv.set_defaults(func=lambda a: print(json.dumps(revoke(a.artifact, a.user), indent=2)))

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
