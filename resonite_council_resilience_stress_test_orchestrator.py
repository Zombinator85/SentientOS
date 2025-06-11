from admin_utils import require_admin_banner, require_lumos_approval
"""Resonite Council Resilience Stress-Test Orchestrator

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path


import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_council_resilience_stress_test_orchestrator.jsonl", "RESONITE_STRESS_TEST_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def start_test(name: str, params: str) -> Dict[str, str]:
    return log_event("start", {"test": name, "params": params})


def report_result(name: str, result: str) -> Dict[str, str]:
    return log_event("result", {"test": name, "result": result})


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


@app.route("/start", methods=["POST"])
def api_start() -> str:
    data = request.get_json() or {}
    return jsonify(start_test(str(data.get("name")), str(data.get("params"))))


@app.route("/result", methods=["POST"])
def api_result() -> str:
    data = request.get_json() or {}
    return jsonify(report_result(str(data.get("name")), str(data.get("result"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    action = data.get("action")
    if action == "start":
        return start_test(data.get("name", ""), data.get("params", ""))
    if action == "result":
        return report_result(data.get("name", ""), data.get("result", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Council Resilience Stress-Test Orchestrator")
    sub = ap.add_subparsers(dest="cmd")

    st = sub.add_parser("start", help="Start stress test")
    st.add_argument("name")
    st.add_argument("params")
    st.set_defaults(func=lambda a: print(json.dumps(start_test(a.name, a.params), indent=2)))

    rs = sub.add_parser("result", help="Record test result")
    rs.add_argument("name")
    rs.add_argument("result")
    rs.set_defaults(func=lambda a: print(json.dumps(report_result(a.name, a.result), indent=2)))

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
