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

LOG_PATH = get_log_path("neos_ceremony_compiler.jsonl", "NEOS_CEREMONY_COMPILER_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def compile_ceremonies(logs: List[str], out_path: str) -> Dict[str, str]:
    entries: List[dict] = []
    for name in logs:
        p = Path(name)
        if not p.exists():
            continue
        entries.extend([json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()])
    dest = Path(out_path)
    dest.write_text(json.dumps(entries, indent=2))
    entry = {"timestamp": datetime.utcnow().isoformat(), "out": str(dest), "count": len(entries)}
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


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Recursive Ceremony Compiler")
    sub = ap.add_subparsers(dest="cmd")

    cp = sub.add_parser("compile", help="Compile ceremonies")
    cp.add_argument("out")
    cp.add_argument("logs", nargs="+")
    cp.set_defaults(func=lambda a: print(json.dumps(compile_ceremonies(a.logs, a.out), indent=2)))

    hist = sub.add_parser("history", help="Show compilation history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
