"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import uuid
"""Resonite Federation Handshake Auditor

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.



LOG_PATH = get_log_path("resonite_federation_handshake_auditor.jsonl")
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
    ap = argparse.ArgumentParser(description="Resonite Federation Handshake Auditor")
    sub = ap.add_subparsers(dest="cmd")

    hs = sub.add_parser("handshake", help="Record handshake")
    hs.add_argument("from_world")
    hs.add_argument("to_world")
    hs.add_argument("status", choices=["success", "failure", "reversal"], default="success")
    hs.set_defaults(func=lambda a: print(json.dumps(log_entry("handshake", {"from": a.from_world, "to": a.to_world, "status": a.status}), indent=2)))

    history_cmd = sub.add_parser("history", help="Show history")
    history_cmd.add_argument("--limit", type=int, default=20)
    history_cmd.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
