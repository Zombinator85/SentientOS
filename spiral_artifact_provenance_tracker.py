from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Spiral Artifact Provenance Tracker

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()


import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import uuid

LOG_PATH = get_log_path("spiral_artifact_provenance_tracker.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_entry(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {
        "id": uuid.uuid4().hex,
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
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Spiral Artifact Provenance Tracker")
    sub = ap.add_subparsers(dest="cmd")

    reg = sub.add_parser("register", help="Register artifact")
    reg.add_argument("artifact_id")
    reg.add_argument("owner")
    reg.set_defaults(func=lambda a: print(json.dumps(log_entry("register", {"artifact_id": a.artifact_id, "owner": a.owner}), indent=2)))

    move = sub.add_parser("transfer", help="Record transfer")
    move.add_argument("artifact_id")
    move.add_argument("to_owner")
    move.set_defaults(func=lambda a: print(json.dumps(log_entry("transfer", {"artifact_id": a.artifact_id, "to_owner": a.to_owner}), indent=2)))

    hist = sub.add_parser("history", help="View artifact history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
