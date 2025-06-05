from admin_utils import require_admin_banner, require_lumos_approval
"""Resonite Council Law Vault & Amendment Engine

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

from __future__ import annotations
from logging_config import get_log_path


import argparse
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_council_law_vault_engine.jsonl", "RESONITE_LAW_VAULT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_event(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        **data,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def propose_law(title: str, text: str, author: str) -> Dict[str, str]:
    law_id = str(uuid.uuid4())
    return log_event("propose", {"id": law_id, "title": title, "text": text, "author": author})


def amend_law(law_id: str, amendment: str, author: str) -> Dict[str, str]:
    return log_event("amend", {"id": law_id, "amendment": amendment, "author": author})


def freeze_law(law_id: str, author: str) -> Dict[str, str]:
    return log_event("freeze", {"id": law_id, "author": author})


def revoke_law(law_id: str, author: str) -> Dict[str, str]:
    return log_event("revoke", {"id": law_id, "author": author})


def seal(law_id: str, quorum: str, intention: str) -> Dict[str, str]:
    return log_event("seal", {"id": law_id, "quorum": quorum, "intention": intention})


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


@app.route("/propose", methods=["POST"])
def api_propose() -> str:
    data = request.get_json() or {}
    return jsonify(propose_law(str(data.get("title")), str(data.get("text")), str(data.get("author"))))


@app.route("/amend", methods=["POST"])
def api_amend() -> str:
    data = request.get_json() or {}
    return jsonify(amend_law(str(data.get("id")), str(data.get("amendment")), str(data.get("author"))))


@app.route("/freeze", methods=["POST"])
def api_freeze() -> str:
    data = request.get_json() or {}
    return jsonify(freeze_law(str(data.get("id")), str(data.get("author"))))


@app.route("/revoke", methods=["POST"])
def api_revoke() -> str:
    data = request.get_json() or {}
    return jsonify(revoke_law(str(data.get("id")), str(data.get("author"))))


@app.route("/seal", methods=["POST"])
def api_seal() -> str:
    data = request.get_json() or {}
    return jsonify(seal(str(data.get("id")), str(data.get("quorum")), str(data.get("intention"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux hook

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    action = data.get("action")
    if action == "propose":
        return propose_law(data.get("title", ""), data.get("text", ""), data.get("author", ""))
    if action == "amend":
        return amend_law(data.get("id", ""), data.get("amendment", ""), data.get("author", ""))
    if action == "freeze":
        return freeze_law(data.get("id", ""), data.get("author", ""))
    if action == "revoke":
        return revoke_law(data.get("id", ""), data.get("author", ""))
    if action == "seal":
        return seal(data.get("id", ""), data.get("quorum", ""), data.get("intention", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Council Law Vault & Amendment Engine")
    sub = ap.add_subparsers(dest="cmd")

    pp = sub.add_parser("propose", help="Propose a new law")
    pp.add_argument("title")
    pp.add_argument("text")
    pp.add_argument("author")
    pp.set_defaults(func=lambda a: print(json.dumps(propose_law(a.title, a.text, a.author), indent=2)))

    am = sub.add_parser("amend", help="Amend existing law")
    am.add_argument("id")
    am.add_argument("amendment")
    am.add_argument("author")
    am.set_defaults(func=lambda a: print(json.dumps(amend_law(a.id, a.amendment, a.author), indent=2)))

    fr = sub.add_parser("freeze", help="Freeze a law")
    fr.add_argument("id")
    fr.add_argument("author")
    fr.set_defaults(func=lambda a: print(json.dumps(freeze_law(a.id, a.author), indent=2)))

    rv = sub.add_parser("revoke", help="Revoke a law")
    rv.add_argument("id")
    rv.add_argument("author")
    rv.set_defaults(func=lambda a: print(json.dumps(revoke_law(a.id, a.author), indent=2)))

    sl = sub.add_parser("seal", help="Seal amendment")
    sl.add_argument("id")
    sl.add_argument("quorum")
    sl.add_argument("intention")
    sl.set_defaults(func=lambda a: print(json.dumps(seal(a.id, a.quorum, a.intention), indent=2)))

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
