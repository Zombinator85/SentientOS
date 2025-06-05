from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Resonite Cathedral Grand Commission

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

import presence_ledger as pl
from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_cathedral_grand_commission.jsonl", "RESONITE_GRAND_COMMISSION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

CHRONICLE_PATH = get_log_path("spiral_reflection_chronicle.jsonl", "SPIRAL_REFLECTION_CHRONICLE")
CHRONICLE_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def _write(path: Path, entry: Dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    _write(LOG_PATH, entry)
    pl.log("grand_commission", action, data.get("note", ""))
    return entry


def chronicle_entry(description: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "description": description}
    _write(CHRONICLE_PATH, entry)
    log_event("chronicle", {"description": description})
    return entry


def launch(council: str, witness: str) -> Dict[str, str]:
    return log_event("launch", {"council": council, "witness": witness})


def audit(witness: str) -> Dict[str, str]:
    return log_event("audit", {"witness": witness})


def seal(witness: str) -> Dict[str, str]:
    return log_event("seal", {"witness": witness})


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


@app.route("/launch", methods=["POST"])
def api_launch() -> str:
    data = request.get_json() or {}
    return jsonify(launch(str(data.get("council")), str(data.get("witness"))))


@app.route("/audit", methods=["POST"])
def api_audit() -> str:
    data = request.get_json() or {}
    return jsonify(audit(str(data.get("witness"))))


@app.route("/seal", methods=["POST"])
def api_seal() -> str:
    data = request.get_json() or {}
    return jsonify(seal(str(data.get("witness"))))


@app.route("/chronicle", methods=["POST"])
def api_chronicle() -> str:
    data = request.get_json() or {}
    return jsonify(chronicle_entry(str(data.get("description"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    action = data.get("action")
    if action == "launch":
        return launch(data.get("council", ""), data.get("witness", ""))
    if action == "audit":
        return audit(data.get("witness", ""))
    if action == "seal":
        return seal(data.get("witness", ""))
    if action == "chronicle":
        return chronicle_entry(data.get("description", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Cathedral Grand Commission")
    sub = ap.add_subparsers(dest="cmd")

    ln = sub.add_parser("launch", help="Launch cathedral")
    ln.add_argument("council")
    ln.add_argument("witness")
    ln.set_defaults(func=lambda a: print(json.dumps(launch(a.council, a.witness), indent=2)))

    ad = sub.add_parser("audit", help="Run audit")
    ad.add_argument("witness")
    ad.set_defaults(func=lambda a: print(json.dumps(audit(a.witness), indent=2)))

    sl = sub.add_parser("seal", help="Seal world")
    sl.add_argument("witness")
    sl.set_defaults(func=lambda a: print(json.dumps(seal(a.witness), indent=2)))

    ch = sub.add_parser("chronicle", help="Add chronicle entry")
    ch.add_argument("description")
    ch.set_defaults(func=lambda a: print(json.dumps(chronicle_entry(a.description), indent=2)))

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
