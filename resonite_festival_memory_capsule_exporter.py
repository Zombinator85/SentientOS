from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner, require_lumos_approval
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

LOG_PATH = get_log_path("resonite_festival_memory_export.jsonl", "RESONITE_MEMORY_EXPORT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_export(creator: str, capsule: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "creator": creator,
        "capsule": capsule,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


@app.route("/export", methods=["POST"])
def api_export() -> str:
    data = request.get_json() or {}
    return jsonify(log_export(str(data.get("creator")), str(data.get("capsule"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_export(data.get("creator", ""), data.get("capsule", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Festival Memory Capsule Exporter")
    sub = ap.add_subparsers(dest="cmd")

    exp = sub.add_parser("export", help="Export capsule")
    exp.add_argument("creator")
    exp.add_argument("capsule")
    exp.set_defaults(func=lambda a: print(json.dumps(log_export(a.creator, a.capsule), indent=2)))

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
