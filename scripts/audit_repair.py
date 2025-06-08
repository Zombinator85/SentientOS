from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
from typing import Tuple

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Banner: requires admin & Lumos approval."""

require_admin_banner()
require_lumos_approval()


def compute_hash(timestamp: str, data: dict, prev_hash: str) -> str:
    """Return SHA256 hash of the audit entry."""
    h = hashlib.sha256()
    h.update(timestamp.encode("utf-8"))
    h.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    h.update(prev_hash.encode("utf-8"))
    return h.hexdigest()


def repair_log(path: Path, prev: str) -> Tuple[str, int]:
    """Repair ``path`` starting from ``prev``.

    Returns the last rolling hash and the number of entries modified.
    """
    lines = [
        json.loads(l)
        for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    repaired = []
    fixed = 0
    for entry in lines:
        changed = False
        if "timestamp" not in entry or "data" not in entry:
            repaired.append(entry)
            prev = entry.get("rolling_hash", prev)
            continue
        if entry.get("prev_hash") != prev:
            entry["prev_hash"] = prev
            changed = True
        digest = compute_hash(entry["timestamp"], entry["data"], prev)
        if entry.get("rolling_hash") != digest:
            entry["rolling_hash"] = digest
            changed = True
        repaired.append(entry)
        prev = digest
        if changed:
            fixed += 1
    with path.open("w", encoding="utf-8") as f:
        for e in repaired:
            f.write(json.dumps(e) + "\n")
    return prev, fixed


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Repair audit log chains")
    ap.add_argument("--logs-dir", default="logs", help="directory of logs")
    ap.add_argument(
        "--auto-approve",
        action="store_true",
        help="skip prompts (or set LUMOS_AUTO_APPROVE=1)",
    )
    args = ap.parse_args(argv)

    if args.auto_approve or os.getenv("LUMOS_AUTO_APPROVE") == "1":
        os.environ["LUMOS_AUTO_APPROVE"] = "1"

    logs_dir = Path(args.logs_dir)
    prev = "0" * 64
    for log in sorted(logs_dir.glob("*.jsonl")):
        prev, fixed = repair_log(log, prev)
        print(f"Fixed {fixed} entries in {log.name}")
    print("\N{WHITE HEAVY CHECK MARK} All logs repaired.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
