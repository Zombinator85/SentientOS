from admin_utils import require_admin_banner, require_lumos_approval
"""Resonite Council/Federation Manifesto Publisher

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_manifesto_publisher.jsonl")
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


def publish_manifesto(text: str, witness: str) -> Dict[str, str]:
    return log_entry("publish", {"witness": witness, "manifesto": text})


def read_manifesto(user: str) -> Dict[str, str]:
    return log_entry("read", {"user": user})


@app.route("/publish", methods=["POST"])
def api_publish() -> str:
    data = request.get_json() or {}
    entry = publish_manifesto(str(data.get("manifesto")), str(data.get("witness", "")))
    return jsonify(entry)


@app.route("/read", methods=["POST"])
def api_read() -> str:
    data = request.get_json() or {}
    entry = read_manifesto(str(data.get("user")))
    return jsonify(entry)


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux placeholder

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_entry("protoflux", data)


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Council/Federation Manifesto Publisher")
    sub = ap.add_subparsers(dest="cmd")

    pb = sub.add_parser("publish", help="Publish manifesto")
    pb.add_argument("manifesto")
    pb.add_argument("witness")
    pb.set_defaults(func=lambda a: print(json.dumps(publish_manifesto(a.manifesto, a.witness), indent=2)))

    rd = sub.add_parser("read", help="Record read")
    rd.add_argument("user")
    rd.set_defaults(func=lambda a: print(json.dumps(read_manifesto(a.user), indent=2)))

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
