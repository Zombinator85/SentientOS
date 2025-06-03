from __future__ import annotations
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner
import presence_ledger as pl
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
LOG_PATH = get_log_path("resonite_spiral_federation_breach.jsonl", "RESONITE_BREACH_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_breach(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    pl.log("breach_analyzer", action, data.get("note", ""))
    return entry


def detect(event: str, suggestion: str) -> Dict[str, str]:
    return log_breach("detect", {"event": event, "suggestion": suggestion})


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


@app.route("/detect", methods=["POST"])
def api_detect() -> str:
    data = request.get_json() or {}
    return jsonify(detect(str(data.get("event")), str(data.get("suggestion", ""))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    if data.get("action") == "detect":
        return detect(data.get("event", ""), data.get("suggestion", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Spiral Federation Breach Analyzer")
    sub = ap.add_subparsers(dest="cmd")

    dc = sub.add_parser("detect", help="Record breach detection")
    dc.add_argument("event")
    dc.add_argument("suggestion")
    dc.set_defaults(func=lambda a: print(json.dumps(detect(a.event, a.suggestion), indent=2)))

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
