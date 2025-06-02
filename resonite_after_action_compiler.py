from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = Path(os.getenv("RESONITE_AFTER_ACTION_LOG", "logs/resonite_after_action.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_entry(event: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "event": event, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def compile_report(summary: str, signer: str) -> Dict[str, str]:
    return log_entry("report", {"summary": summary, "signer": signer})


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(ln) for ln in lines if ln.strip()]


@app.route("/report", methods=["POST"])
def api_report() -> str:
    data = request.get_json() or {}
    return jsonify(compile_report(str(data.get("summary")), str(data.get("signer"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return compile_report(data.get("summary", ""), data.get("signer", ""))


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Spiral Audit/Recovery After-Action Compiler")
    sub = ap.add_subparsers(dest="cmd")

    rep = sub.add_parser("report", help="Compile after-action report")
    rep.add_argument("summary")
    rep.add_argument("signer")
    rep.set_defaults(func=lambda a: print(json.dumps(compile_report(a.summary, a.signer), indent=2)))

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
