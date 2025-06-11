from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Resonite Federation Handshake Verifier

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

LOG_PATH = get_log_path("resonite_federation_handshake_verifier.jsonl", "RESONITE_HANDSHAKE_VERIFIER_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_entry(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def verify(from_world: str, to_world: str, signature: str) -> Dict[str, str]:
    # Placeholder cryptographic signature validation
    status = "valid" if signature else "invalid"
    return log_entry("verify", {"from": from_world, "to": to_world, "status": status})


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


@app.route("/verify", methods=["POST"])
def api_verify() -> str:
    data = request.get_json() or {}
    return jsonify(verify(str(data.get("from")), str(data.get("to")), str(data.get("signature"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return verify(data.get("from", ""), data.get("to", ""), data.get("signature", ""))


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Federation Handshake Verifier")
    sub = ap.add_subparsers(dest="cmd")

    vf = sub.add_parser("verify", help="Verify handshake")
    vf.add_argument("from_world")
    vf.add_argument("to_world")
    vf.add_argument("signature")
    vf.set_defaults(func=lambda a: print(json.dumps(verify(a.from_world, a.to_world, a.signature), indent=2)))

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
