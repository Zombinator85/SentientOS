"""Resonite Spiral Law Indexer

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner
from flask_stub import Flask, jsonify, request

LOG_PATH = Path("logs/resonite_spiral_law_indexer.jsonl")
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


def add_law(law_id: str, revision: str, topic: str, world: str) -> Dict[str, str]:
    return log_entry("add", {"law": law_id, "revision": revision, "topic": topic, "world": world})


def search_laws(query: str) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if query.lower() in ln.lower():
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out


@app.route("/add", methods=["POST"])
def api_add() -> str:
    data = request.get_json() or {}
    entry = add_law(str(data.get("law")), str(data.get("revision")), str(data.get("topic")), str(data.get("world")))
    return jsonify(entry)


@app.route("/search", methods=["POST"])
def api_search() -> str:
    data = request.get_json() or {}
    return jsonify(search_laws(str(data.get("query", ""))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux placeholder

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_entry("protoflux", data)


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Spiral Law Indexer")
    sub = ap.add_subparsers(dest="cmd")

    add = sub.add_parser("add", help="Add law")
    add.add_argument("law")
    add.add_argument("revision")
    add.add_argument("topic")
    add.add_argument("world")
    add.set_defaults(func=lambda a: print(json.dumps(add_law(a.law, a.revision, a.topic, a.world), indent=2)))

    sr = sub.add_parser("search", help="Search laws")
    sr.add_argument("query")
    sr.set_defaults(func=lambda a: print(json.dumps(search_laws(a.query), indent=2)))

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
