from admin_utils import require_admin_banner
"""Resonite Artifact License/Provenance Registry

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_artifact_provenance_registry.jsonl")
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


def register_artifact(artifact: str, origin: str, license_: str) -> Dict[str, str]:
    return log_entry("register", {"artifact": artifact, "origin": origin, "license": license_})


def update_artifact(artifact: str, field: str, value: str) -> Dict[str, str]:
    return log_entry("update", {"artifact": artifact, "field": field, "value": value})


def query_artifact(artifact: str) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if f'"artifact": "{artifact}"' in ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out


@app.route("/register", methods=["POST"])
def api_register() -> str:
    data = request.get_json() or {}
    entry = register_artifact(str(data.get("artifact")), str(data.get("origin")), str(data.get("license", "")))
    return jsonify(entry)


@app.route("/update", methods=["POST"])
def api_update() -> str:
    data = request.get_json() or {}
    entry = update_artifact(str(data.get("artifact")), str(data.get("field")), str(data.get("value")))
    return jsonify(entry)


@app.route("/query", methods=["POST"])
def api_query() -> str:
    data = request.get_json() or {}
    return jsonify(query_artifact(str(data.get("artifact"))))


# ProtoFlux placeholder

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_entry("protoflux", data)


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Artifact License/Provenance Registry")
    sub = ap.add_subparsers(dest="cmd")

    reg = sub.add_parser("register", help="Register artifact")
    reg.add_argument("artifact")
    reg.add_argument("origin")
    reg.add_argument("license")
    reg.set_defaults(func=lambda a: print(json.dumps(register_artifact(a.artifact, a.origin, a.license), indent=2)))

    up = sub.add_parser("update", help="Update artifact")
    up.add_argument("artifact")
    up.add_argument("field")
    up.add_argument("value")
    up.set_defaults(func=lambda a: print(json.dumps(update_artifact(a.artifact, a.field, a.value), indent=2)))

    q = sub.add_parser("query", help="Query artifact")
    q.add_argument("artifact")
    q.set_defaults(func=lambda a: print(json.dumps(query_artifact(a.artifact), indent=2)))

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
