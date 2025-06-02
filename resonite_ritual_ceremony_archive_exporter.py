from __future__ import annotations
from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner
import presence_ledger as pl
from flask_stub import Flask, jsonify, request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
LOG_PATH = get_log_path("resonite_ritual_ceremony_archive_export.jsonl", "RESONITE_ARCHIVE_EXPORT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_export(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    pl.log("archive_export", action, data.get("note", ""))
    return entry


def export_archive(curator: str) -> Dict[str, str]:
    return log_export("export", {"curator": curator})


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


@app.route("/export", methods=["POST"])
def api_export() -> str:
    data = request.get_json() or {}
    return jsonify(export_archive(str(data.get("curator"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    if data.get("action") == "export":
        return export_archive(data.get("curator", ""))
    return {"error": "unknown action"}


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Resonite Ritual Ceremony Archive Exporter")
    sub = ap.add_subparsers(dest="cmd")

    ex = sub.add_parser("export", help="Export archive")
    ex.add_argument("curator")
    ex.set_defaults(func=lambda a: print(json.dumps(export_archive(a.curator), indent=2)))

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
