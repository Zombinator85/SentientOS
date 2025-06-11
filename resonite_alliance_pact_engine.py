from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Resonite Alliance Pact Engine

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

LOG_PATH = get_log_path("alliance_pact_log.jsonl")
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
    ap = argparse.ArgumentParser(description="Resonite Alliance Pact Engine")
    sub = ap.add_subparsers(dest="cmd")

    dr = sub.add_parser("draft", help="Draft alliance pact")
    dr.add_argument("title")
    dr.add_argument("text")
    dr.set_defaults(func=lambda a: print(json.dumps(log_entry("draft", {"title": a.title, "text": a.text}), indent=2)))

    sg = sub.add_parser("sign", help="Sign alliance pact")
    sg.add_argument("pact_id")
    sg.add_argument("signer")
    sg.set_defaults(func=lambda a: print(json.dumps(log_entry("sign", {"pact_id": a.pact_id, "signer": a.signer}), indent=2)))

    rv = sub.add_parser("review", help="Review pact history")
    rv.add_argument("--limit", type=int, default=20)
    rv.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
