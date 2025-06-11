from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Festival/Federation Presence Diff Engine
Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List
from datetime import datetime

LOG_PATH = get_log_path("presence_diff.jsonl", "PRESENCE_DIFF_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def diff(a: Path, b: Path) -> Dict[str, str]:
    data_a = set(a.read_text(encoding="utf-8").splitlines()) if a.exists() else set()
    data_b = set(b.read_text(encoding="utf-8").splitlines()) if b.exists() else set()
    missing = sorted(data_a.symmetric_difference(data_b))
    entry = {"timestamp": datetime.utcnow().isoformat(), "file_a": str(a), "file_b": str(b), "diff": missing}
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
    ap = argparse.ArgumentParser(description="Festival/Federation Presence Diff Engine")
    sub = ap.add_subparsers(dest="cmd")

    df = sub.add_parser("diff", help="Compare presence files")
    df.add_argument("file_a")
    df.add_argument("file_b")
    df.set_defaults(func=lambda a: print(json.dumps(diff(Path(a.file_a), Path(a.file_b)), indent=2)))

    hs = sub.add_parser("history", help="Show diff history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
