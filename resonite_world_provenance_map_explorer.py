"""Resonite Ceremony/World Provenance Map Explorer

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_world_provenance_map_explorer.jsonl", "RESONITE_WORLD_PROVENANCE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def map_entity(entity: str, origin: str, blessing: str) -> Dict[str, str]:
    return log_event("map", {"entity": entity, "origin": origin, "blessing": blessing})


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


@app.route("/map", methods=["POST"])
def api_map() -> str:
    data = request.get_json() or {}
    return jsonify(map_entity(str(data.get("entity")), str(data.get("origin")), str(data.get("blessing"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return map_entity(data.get("entity", ""), data.get("origin", ""), data.get("blessing", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Ceremony/World Provenance Map Explorer")
    sub = ap.add_subparsers(dest="cmd")

    mp = sub.add_parser("map", help="Map entity provenance")
    mp.add_argument("entity")
    mp.add_argument("origin")
    mp.add_argument("blessing")
    mp.set_defaults(func=lambda a: print(json.dumps(map_entity(a.entity, a.origin, a.blessing), indent=2)))

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
