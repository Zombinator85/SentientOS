"""Resonite Sanctuary Emergency Posture Engine

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from __future__ import annotations

from admin_utils import require_admin_banner

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
from logging_config import get_log_path

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_sanctuary_emergency_posture.jsonl")
STATE_FILE = Path("state/resonite_sanctuary_emergency.state")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

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


def activate(reason: str) -> Dict[str, str]:
    STATE_FILE.write_text("active")
    return log_entry("activate", {"reason": reason})


def deactivate() -> Dict[str, str]:
    STATE_FILE.write_text("inactive")
    return log_entry("deactivate", {})


def status() -> Dict[str, str]:
    state = STATE_FILE.read_text() if STATE_FILE.exists() else "inactive"
    return {"state": state.strip()}


@app.route("/activate", methods=["POST"])
def api_activate() -> str:
    data = request.get_json() or {}
    entry = activate(str(data.get("reason", "")))
    return jsonify(entry)


@app.route("/deactivate", methods=["POST"])
def api_deactivate() -> str:
    deactivate()
    return jsonify({"status": "ok"})


@app.route("/status", methods=["POST"])
def api_status() -> str:
    return jsonify(status())


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux placeholder

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_entry("protoflux", data)


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Sanctuary Emergency Posture Engine")
    sub = ap.add_subparsers(dest="cmd")

    ac = sub.add_parser("activate", help="Activate emergency")
    ac.add_argument("reason")
    ac.set_defaults(func=lambda a: print(json.dumps(activate(a.reason), indent=2)))

    de = sub.add_parser("deactivate", help="Deactivate emergency")
    de.set_defaults(func=lambda a: print(json.dumps(deactivate(), indent=2)))

    st = sub.add_parser("status", help="Show status")
    st.set_defaults(func=lambda a: print(json.dumps(status(), indent=2)))

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
