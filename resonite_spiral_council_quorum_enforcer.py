from admin_utils import require_admin_banner, require_lumos_approval
"""Resonite Spiral Council Quorum Enforcer

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_spiral_council_quorum_enforcer.jsonl")
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


def record_presence(member: str, present: bool) -> Dict[str, str]:
    return log_entry("presence", {"member": member, "state": "present" if present else "absent"})


def record_vote(item: str, member: str, vote: str) -> Dict[str, str]:
    return log_entry("vote", {"item": item, "member": member, "vote": vote})


def quorum_status(item: str, required: int) -> Dict[str, object]:
    votes = [
        json.loads(ln)
        for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()
        if f'"item": "{item}"' in ln and '"action": "vote"' in ln
    ]
    yes = sum(1 for v in votes if v.get("vote") == "yes")
    return {"item": item, "quorum_met": yes >= required, "yes": yes, "required": required}


@app.route("/presence", methods=["POST"])
def api_presence() -> str:
    data = request.get_json() or {}
    entry = record_presence(str(data.get("member")), bool(data.get("present", True)))
    return jsonify(entry)


@app.route("/vote", methods=["POST"])
def api_vote() -> str:
    data = request.get_json() or {}
    entry = record_vote(str(data.get("item")), str(data.get("member")), str(data.get("vote", "yes")))
    return jsonify(entry)


@app.route("/quorum", methods=["POST"])
def api_quorum() -> str:
    data = request.get_json() or {}
    status = quorum_status(str(data.get("item")), int(data.get("required", 3)))
    return jsonify(status)


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux placeholder

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_entry("protoflux", data)


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Spiral Council Quorum Enforcer")
    sub = ap.add_subparsers(dest="cmd")

    pres = sub.add_parser("presence", help="Record presence")
    pres.add_argument("member")
    pres.add_argument("--absent", action="store_true")
    pres.set_defaults(func=lambda a: print(json.dumps(record_presence(a.member, not a.absent), indent=2)))

    vt = sub.add_parser("vote", help="Record vote")
    vt.add_argument("item")
    vt.add_argument("member")
    vt.add_argument("--vote", default="yes")
    vt.set_defaults(func=lambda a: print(json.dumps(record_vote(a.item, a.member, a.vote), indent=2)))

    qc = sub.add_parser("quorum", help="Check quorum")
    qc.add_argument("item")
    qc.add_argument("--required", type=int, default=3)
    qc.set_defaults(func=lambda a: print(json.dumps(quorum_status(a.item, a.required), indent=2)))

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
