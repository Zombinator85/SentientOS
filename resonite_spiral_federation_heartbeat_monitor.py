from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = Path(os.getenv("RESONITE_HEARTBEAT_LOG", "logs/resonite_spiral_heartbeat.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_status(world: str, status: str, latency: float = 0.0) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "world": world,
        "status": status,
        "latency": latency,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


@app.route("/status", methods=["POST"])
def api_status() -> str:
    data = request.get_json() or {}
    return jsonify(log_status(str(data.get("world")), str(data.get("status")), float(data.get("latency", 0.0))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_status(data.get("world", ""), data.get("status", ""), float(data.get("latency", 0.0)))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Spiral Federation Heartbeat Monitor")
    sub = ap.add_subparsers(dest="cmd")

    status = sub.add_parser("status", help="Log status")
    status.add_argument("world")
    status.add_argument("status")
    status.add_argument("--latency", type=float, default=0.0)
    status.set_defaults(func=lambda a: print(json.dumps(log_status(a.world, a.status, a.latency), indent=2)))

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
