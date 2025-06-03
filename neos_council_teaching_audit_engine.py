from __future__ import annotations
from admin_utils import require_admin_banner
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

SESSIONS_LOG = get_log_path("neos_council_teaching_sessions.jsonl", "NEOS_COUNCIL_TEACHING_SESSIONS_LOG")
AUDIT_LOG = get_log_path("neos_council_teaching_audit.jsonl", "NEOS_COUNCIL_TEACHING_AUDIT_LOG")
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)


def audit_sessions() -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    if SESSIONS_LOG.exists():
        for line in SESSIONS_LOG.read_text(encoding="utf-8").splitlines():
            try:
                sess = json.loads(line)
            except Exception:
                continue
            flag = None
            status = sess.get("status")
            if status != "complete":
                flag = "incomplete" if status != "drifted" else "drifted"
            if flag:
                entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "session": sess,
                    "flag": flag,
                }
                entries.append(entry)
                with AUDIT_LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
    return entries


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not AUDIT_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in AUDIT_LOG.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Council Teaching Audit Engine")
    sub = ap.add_subparsers(dest="cmd")

    runp = sub.add_parser("run", help="Run audit")
    runp.set_defaults(func=lambda a: print(json.dumps(audit_sessions(), indent=2)))

    hist = sub.add_parser("history", help="Show audit history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
