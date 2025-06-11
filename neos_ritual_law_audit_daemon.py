"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
from admin_utils import require_admin_banner, require_lumos_approval
import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from log_utils import append_json, read_json

"""NeosVR Ritual Law Audit & Remediation Daemon.

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.



LOG_PATH = get_log_path("neos_ritual_audit.jsonl", "NEOS_RITUAL_AUDIT_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_audit(issue: str, proposal: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "issue": issue,
        "proposal": proposal,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_audits(term: str = "") -> List[Dict[str, str]]:
    audits = read_json(LOG_PATH)
    if term:
        audits = [a for a in audits if term in json.dumps(a)]
    return audits


def run_daemon(interval: float) -> None:
    while True:
        log_audit("heartbeat")
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Ritual Law Audit Daemon")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log audit issue")
    lg.add_argument("issue")
    lg.add_argument("--proposal", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_audit(a.issue, a.proposal), indent=2)))

    ls = sub.add_parser("list", help="List audits")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_audits(a.term), indent=2)))

    rn = sub.add_parser("run", help="Run continuous audit daemon")
    rn.add_argument("--interval", type=float, default=60.0)
    rn.set_defaults(func=lambda a: run_daemon(a.interval))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
