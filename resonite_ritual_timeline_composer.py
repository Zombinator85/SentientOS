from admin_utils import require_admin_banner, require_lumos_approval
"""Resonite Onboarding/Festival Ritual Timeline Composer

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
from typing import Any, Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_ritual_timeline_composer.jsonl", "RESONITE_TIMELINE_COMPOSER_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, Any]) -> Dict[str, Any]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def compose_timeline(name: str, events: List[str]) -> Dict[str, Any]:
    return log_event("compose", {"name": name, "events": events})


def history(limit: int = 20) -> List[Dict[str, Any]]:
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


@app.route("/compose", methods=["POST"])
def api_compose() -> str:
    data = request.get_json() or {}
    events = data.get("events") or []
    if not isinstance(events, list):
        events = [str(events)]
    return jsonify(compose_timeline(str(data.get("name")), [str(e) for e in events]))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, Any]:
    events_raw = data.get("events")
    if isinstance(events_raw, list):
        events: List[str] = [str(e) for e in events_raw]
    elif events_raw is not None:
        events = [str(events_raw)]
    else:
        events = []
    return compose_timeline(data.get("name", ""), events)


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Onboarding/Festival Ritual Timeline Composer")
    sub = ap.add_subparsers(dest="cmd")

    cp = sub.add_parser("compose", help="Compose timeline")
    cp.add_argument("name")
    cp.add_argument("events", nargs="+")
    cp.set_defaults(func=lambda a: print(json.dumps(compose_timeline(a.name, a.events), indent=2)))

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
