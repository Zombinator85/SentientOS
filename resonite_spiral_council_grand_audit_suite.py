"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from admin_utils import require_admin_banner, require_lumos_approval
import presence_ledger as pl
from flask_stub import Flask, jsonify, request
require_admin_banner()
require_lumos_approval()
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
LOG_PATH = get_log_path("resonite_spiral_council_grand_audit.jsonl", "RESONITE_GRAND_AUDIT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_audit(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    pl.log("grand_audit", action, data.get("note", ""))
    return entry


def run_audit(witness: str) -> Dict[str, str]:
    return log_audit("run", {"witness": witness})


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


@app.route("/run", methods=["POST"])
def api_run() -> str:
    data = request.get_json() or {}
    return jsonify(run_audit(str(data.get("witness"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    if data.get("action") == "run":
        return run_audit(data.get("witness", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Spiral Council Grand Audit Suite")
    sub = ap.add_subparsers(dest="cmd")

    rn = sub.add_parser("run", help="Run full audit")
    rn.add_argument("witness")
    rn.set_defaults(func=lambda a: print(json.dumps(run_audit(a.witness), indent=2)))

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
