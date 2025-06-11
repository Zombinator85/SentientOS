from __future__ import annotations
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from sentientos.privilege import require_admin_banner, require_lumos_approval
import presence_ledger as pl
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
LOG_PATH = get_log_path("resonite_public_law_artifact_changelog.jsonl", "RESONITE_CHANGELOG_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_change(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    pl.log("changelog", action, data.get("item", ""))
    return entry


def notify_change(item: str, author: str) -> Dict[str, str]:
    return log_change("notify", {"item": item, "author": author})


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


@app.route("/notify", methods=["POST"])
def api_notify() -> str:
    data = request.get_json() or {}
    return jsonify(notify_change(str(data.get("item")), str(data.get("author"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    if data.get("action") == "notify":
        return notify_change(data.get("item", ""), data.get("author", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite Public Law/Artifact Changelog Notifier")
    sub = ap.add_subparsers(dest="cmd")

    nt = sub.add_parser("notify", help="Notify change")
    nt.add_argument("item")
    nt.add_argument("author")
    nt.set_defaults(func=lambda a: print(json.dumps(notify_change(a.item, a.author), indent=2)))

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
