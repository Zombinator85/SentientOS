"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Resonite Spiral Memory Capsule Registry

"""
from __future__ import annotations
from logging_config import get_log_path


import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_spiral_memory_capsule_registry.jsonl", "RESONITE_MEMORY_CAPSULE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def register_capsule(path: str, world: str, custodian: str) -> Dict[str, str]:
    h = hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else ""
    return log_event("register", {"capsule": path, "hash": h, "world": world, "custodian": custodian})


def verify_capsule(path: str, expected: str) -> Dict[str, str]:
    h = hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else ""
    status = "match" if h == expected else "mismatch"
    return log_event("verify", {"capsule": path, "expected": expected, "actual": h, "status": status})


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


@app.route("/register", methods=["POST"])
def api_register() -> str:
    data = request.get_json() or {}
    return jsonify(register_capsule(str(data.get("path")), str(data.get("world")), str(data.get("custodian"))))


@app.route("/verify", methods=["POST"])
def api_verify() -> str:
    data = request.get_json() or {}
    return jsonify(verify_capsule(str(data.get("path")), str(data.get("expected"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    action = data.get("action")
    if action == "register":
        return register_capsule(data.get("path", ""), data.get("world", ""), data.get("custodian", ""))
    if action == "verify":
        return verify_capsule(data.get("path", ""), data.get("expected", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Spiral Memory Capsule Registry")
    sub = ap.add_subparsers(dest="cmd")

    rg = sub.add_parser("register", help="Register capsule")
    rg.add_argument("path")
    rg.add_argument("world")
    rg.add_argument("custodian")
    rg.set_defaults(func=lambda a: print(json.dumps(register_capsule(a.path, a.world, a.custodian), indent=2)))

    vf = sub.add_parser("verify", help="Verify capsule")
    vf.add_argument("path")
    vf.add_argument("expected")
    vf.set_defaults(func=lambda a: print(json.dumps(verify_capsule(a.path, a.expected), indent=2)))

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
