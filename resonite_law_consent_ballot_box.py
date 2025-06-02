from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = get_log_path("resonite_law_consent_ballot_box.jsonl", "RESONITE_BALLOT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_vote(amendment: str, voter: str, vote: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "amendment": amendment,
        "voter": voter,
        "vote": vote,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


@app.route("/vote", methods=["POST"])
def api_vote() -> str:
    data = request.get_json() or {}
    return jsonify(log_vote(str(data.get("amendment")), str(data.get("voter")), str(data.get("vote"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_vote(data.get("amendment", ""), data.get("voter", ""), data.get("vote", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Ritual Law/Consent Amendment Ballot Box")
    sub = ap.add_subparsers(dest="cmd")

    vote_cmd = sub.add_parser("vote", help="Record vote")
    vote_cmd.add_argument("amendment")
    vote_cmd.add_argument("voter")
    vote_cmd.add_argument("vote")
    vote_cmd.set_defaults(func=lambda a: print(json.dumps(log_vote(a.amendment, a.voter, a.vote), indent=2)))

    hist = sub.add_parser("history", help="Show history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
