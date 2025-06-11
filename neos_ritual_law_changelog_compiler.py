from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

CHANGELOG = get_log_path("neos_ritual_law_changelog.jsonl", "NEOS_RITUAL_LAW_CHANGELOG")
CHANGELOG.parent.mkdir(parents=True, exist_ok=True)


def compile_changelog(paths: List[str], dest: str) -> Dict[str, str]:
    events: List[Dict[str, str]] = []
    for name in paths:
        p = Path(name)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    Path(dest).write_text(json.dumps(events, indent=2), encoding="utf-8")
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "dest": dest,
        "events": len(events),
    }
    with CHANGELOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not CHANGELOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in CHANGELOG.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Ritual Law Changelog Compiler")
    sub = ap.add_subparsers(dest="cmd")

    cp = sub.add_parser("compile", help="Compile changelog")
    cp.add_argument("dest")
    cp.add_argument("logs", nargs="+")
    cp.set_defaults(func=lambda a: print(json.dumps(compile_changelog(a.logs, a.dest), indent=2)))

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
