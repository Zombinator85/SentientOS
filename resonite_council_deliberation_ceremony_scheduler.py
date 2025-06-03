from __future__ import annotations
from admin_utils import require_admin_banner
from logging_config import get_log_path

"""Resonite Council Deliberation & Ceremony Scheduler

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.


import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_council_deliberation_ceremony_scheduler.jsonl", "RESONITE_COUNCIL_SCHED_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def schedule(ceremony: str, time: str, proposer: str) -> Dict[str, str]:
    return log_event("schedule", {"ceremony": ceremony, "time": time, "proposer": proposer})


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


@app.route("/schedule", methods=["POST"])
def api_schedule() -> str:
    data = request.get_json() or {}
    return jsonify(schedule(str(data.get("ceremony")), str(data.get("time")), str(data.get("proposer"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return schedule(data.get("ceremony", ""), data.get("time", ""), data.get("proposer", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Council Deliberation & Ceremony Scheduler")
    sub = ap.add_subparsers(dest="cmd")

    sc = sub.add_parser("schedule", help="Schedule ceremony")
    sc.add_argument("ceremony")
    sc.add_argument("time")
    sc.add_argument("proposer")
    sc.set_defaults(func=lambda a: print(json.dumps(schedule(a.ceremony, a.time, a.proposer), indent=2)))

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
