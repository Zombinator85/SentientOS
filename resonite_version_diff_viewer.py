"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Resonite World/Artifact Version Diff Viewer

"""
from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import difflib

from flask_stub import Flask, jsonify, request

LOG_PATH = get_log_path("resonite_version_diff_viewer.jsonl")
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


def diff_files(a: str, b: str) -> Dict[str, str]:
    text1 = Path(a).read_text(encoding="utf-8") if Path(a).exists() else ""
    text2 = Path(b).read_text(encoding="utf-8") if Path(b).exists() else ""
    diff = "\n".join(difflib.unified_diff(text1.splitlines(), text2.splitlines(), lineterm=""))
    log_entry("diff", {"a": a, "b": b})
    return {"diff": diff}


@app.route("/diff", methods=["POST"])
def api_diff() -> str:
    data = request.get_json() or {}
    return jsonify(diff_files(str(data.get("a")), str(data.get("b"))))


@app.route("/history", methods=["POST"])
def api_history() -> str:
    data = request.get_json() or {}
    return jsonify(history(int(data.get("limit", 20))))


# ProtoFlux placeholder

def protoflux_hook(data: Dict[str, str]) -> Dict[str, str]:
    return log_entry("protoflux", data)


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Resonite World/Artifact Version Diff Viewer")
    sub = ap.add_subparsers(dest="cmd")

    df = sub.add_parser("diff", help="Show diff between files")
    df.add_argument("a")
    df.add_argument("b")
    df.set_defaults(func=lambda a: print(json.dumps(diff_files(a.a, a.b), indent=2)))

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
