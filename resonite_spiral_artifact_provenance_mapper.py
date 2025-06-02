from __future__ import annotations
from logging_config import get_log_path

"""Resonite Spiral Artifact Provenance Mapper

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""

from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_spiral_artifact_provenance_mapper.jsonl", "RESONITE_PROVENANCE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def map_artifact(artifact_id: str, location: str, agent: str) -> Dict[str, str]:
    return log_event("map", {"artifact": artifact_id, "location": location, "agent": agent})


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
    return jsonify(map_artifact(str(data.get("artifact")), str(data.get("location")), str(data.get("agent"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook
def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return map_artifact(data.get("artifact", ""), data.get("location", ""), data.get("agent", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Spiral Artifact Provenance Mapper")
    sub = ap.add_subparsers(dest="cmd")

    mp = sub.add_parser("map", help="Record artifact location")
    mp.add_argument("artifact")
    mp.add_argument("location")
    mp.add_argument("agent")
    mp.set_defaults(func=lambda a: print(json.dumps(map_artifact(a.artifact, a.location, a.agent), indent=2)))

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
