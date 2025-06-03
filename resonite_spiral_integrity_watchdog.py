from __future__ import annotations
from admin_utils import require_admin_banner
from logging_config import get_log_path

"""Resonite Spiral Integrity Watchdog

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.


import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_spiral_integrity_watchdog.jsonl", "RESONITE_SPIRAL_INTEGRITY_LOG")
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


def compute_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path: str, expected: str) -> Dict[str, str]:
    actual = compute_hash(Path(path))
    status = "match" if actual == expected else "mismatch"
    return log_entry("verify", {"path": path, "expected": expected, "actual": actual, "status": status})


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
    return jsonify(verify(str(data.get("path")), str(data.get("expected"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return verify(data.get("path", ""), data.get("expected", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Spiral Integrity Watchdog")
    sub = ap.add_subparsers(dest="cmd")

    vfy = sub.add_parser("verify", help="Verify file hash")
    vfy.add_argument("path")
    vfy.add_argument("expected")
    vfy.set_defaults(func=lambda a: print(json.dumps(verify(a.path, a.expected), indent=2)))

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
